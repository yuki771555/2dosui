package jp.twodosumi.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class PiMonitorService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val apiFactory = ApiFactory()
    private var monitorJob: kotlinx.coroutines.Job? = null
    private var baseUrl: String = ""
    private var token: String = ""
    private var alarmVolume: Float = 1.0f
    private var soundEnabled: Boolean = true
    private var alarmNotificationsEnabled: Boolean = true
    private var lastAlarmKey: String? = null
    private var currentAlarmTitle: String = ""
    private var returnedStateAlarmed: Boolean = false
    private var player: MediaPlayer? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        createChannels()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP_ALARM -> stopPhoneAlarm()
            ACTION_TEST_ALARM -> {
                readAlarmOptions(intent)
                startForeground(NOTIFICATION_ID, monitorNotification("監視中", "ラズパイの状態を監視しています"))
                startPhoneAlarm("テストアラーム")
            }
            ACTION_STOP_SERVICE -> {
                stopPhoneAlarm()
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                baseUrl = intent?.getStringExtra(EXTRA_BASE_URL).orEmpty()
                token = intent?.getStringExtra(EXTRA_TOKEN).orEmpty()
                readAlarmOptions(intent)
                startForeground(NOTIFICATION_ID, monitorNotification("監視中", "ラズパイの状態を監視しています"))
                startMonitoring()
            }
        }
        return START_REDELIVER_INTENT
    }

    override fun onDestroy() {
        monitorJob?.cancel()
        stopPhoneAlarm()
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startMonitoring() {
        if (baseUrl.isBlank() || token.isBlank() || monitorJob?.isActive == true) return
        val api = apiFactory.create(baseUrl, token)
        monitorJob = scope.launch {
            while (true) {
                runCatching {
                    val response = api.getStatus().checked()
                    val status = requireNotNull(response.status) { "status is missing" }
                    handleStatus(status)
                }.onFailure {
                    notifyMonitor("接続待機中", it.message ?: "ラズパイに接続できません")
                }
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    private fun handleStatus(status: StatusDto) {
        val pendingRechecks = status.pendingRechecks.orEmpty()
        val offBed = isOffBed(status)
        if (status.state != "RETURNED") {
            returnedStateAlarmed = false
        }
        if (
            offBed ||
            status.event in STOP_EVENTS ||
            (
                player != null &&
                    currentAlarmTitle != "二度寝検知" &&
                    pendingRechecks.isEmpty() &&
                    status.event !in ALARM_EVENTS
                )
        ) {
            stopPhoneAlarm()
            return
        }
        val key = "${status.timestamp.orEmpty()}|${status.event}"
        if (status.event in ALARM_EVENTS && key != lastAlarmKey) {
            lastAlarmKey = key
            startPhoneAlarm(alarmTitle(status.event))
        } else if (status.state == "RETURNED" && !returnedStateAlarmed) {
            returnedStateAlarmed = true
            startPhoneAlarm("再入床")
        } else if (pendingRechecks.isNotEmpty()) {
            val pendingKey = pendingRechecks.joinToString("|") { "${it.time}|${it.label}|${it.realarmCount}" }
            if (pendingKey != lastAlarmKey) {
                lastAlarmKey = pendingKey
                startPhoneAlarm("起床アラーム")
            }
        } else if (player == null) {
            notifyMonitor("監視中", presenceText(status))
        }
    }

    private fun startPhoneAlarm(title: String) {
        stopPhoneAlarm()
        currentAlarmTitle = title
        if (soundEnabled) {
            val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            player = MediaPlayer().apply {
                setDataSource(this@PiMonitorService, uri)
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                isLooping = true
                prepare()
                setVolume(alarmVolume, alarmVolume)
                start()
            }
        }
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "2dosumi:phoneAlarm")
            .apply { acquire(10 * 60 * 1000L) }
        if (alarmNotificationsEnabled) {
            notifyAlarm(title)
        } else {
            notifyMonitor("アラーム発生", title)
        }
    }

    private fun stopPhoneAlarm() {
        player?.let {
            runCatching {
                if (it.isPlaying) it.stop()
            }
            it.release()
        }
        player = null
        wakeLock?.let {
            if (it.isHeld) it.release()
        }
        wakeLock = null
        currentAlarmTitle = ""
        notifyMonitor("監視中", "ラズパイの状態を監視しています")
    }

    private fun notifyMonitor(title: String, text: String) {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, monitorNotification(title, text))
    }

    private fun notifyAlarm(title: String) {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, alarmNotification(title))
    }

    private fun monitorNotification(title: String, text: String): Notification =
        Notification.Builder(this, MONITOR_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(openAppIntent())
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "停止", serviceIntent(ACTION_STOP_SERVICE))
            .build()

    private fun alarmNotification(title: String): Notification =
        Notification.Builder(this, ALARM_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(title)
            .setContentText("スマホでアラームを鳴らしています")
            .setOngoing(true)
            .setCategory(Notification.CATEGORY_ALARM)
            .setContentIntent(openAppIntent())
            .addAction(android.R.drawable.ic_media_pause, "音を止める", serviceIntent(ACTION_STOP_ALARM))
            .build()

    private fun openAppIntent(): PendingIntent {
        val intent = Intent(this, MainActivity::class.java)
        return PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
    }

    private fun serviceIntent(action: String): PendingIntent {
        val intent = Intent(this, PiMonitorService::class.java).setAction(action)
        return PendingIntent.getService(
            this,
            action.hashCode(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
    }

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(
                MONITOR_CHANNEL_ID,
                "2dosumi monitor",
                NotificationManager.IMPORTANCE_LOW,
            )
        )
        manager.createNotificationChannel(
            NotificationChannel(
                ALARM_CHANNEL_ID,
                "2dosumi alarm",
                NotificationManager.IMPORTANCE_HIGH,
            )
        )
    }

    private fun readAlarmOptions(intent: Intent?) {
        alarmVolume = intent?.getFloatExtra(EXTRA_VOLUME, alarmVolume)?.coerceIn(0f, 1f) ?: alarmVolume
        soundEnabled = intent?.getBooleanExtra(EXTRA_SOUND_ENABLED, soundEnabled) ?: soundEnabled
        alarmNotificationsEnabled = intent?.getBooleanExtra(
            EXTRA_ALARM_NOTIFICATIONS_ENABLED,
            alarmNotificationsEnabled,
        ) ?: alarmNotificationsEnabled
    }

    private fun BasicResponse.checked(): BasicResponse {
        if (!ok) throw IllegalStateException(error ?: "request failed")
        return this
    }

    private fun StatusResponse.checked(): StatusResponse {
        if (!ok) throw IllegalStateException(error ?: "request failed")
        return this
    }

    private fun alarmTitle(event: String): String = when (event) {
        "scheduled_alarm" -> "起床アラーム"
        "bed_still_occupied_realarm" -> "再アラーム"
        "returned" -> "再入床"
        "second_sleep_detected" -> "二度寝検知"
        else -> "2dosumiアラーム"
    }

    private fun presenceText(status: StatusDto): String =
        status.smoothedWeightKg?.let { "%.1f kg相当".format(it) } ?: status.message.ifBlank { "監視中" }

    private fun isOffBed(status: StatusDto): Boolean {
        val weight = status.smoothedWeightKg ?: status.weightKg ?: return false
        return weight < DEFAULT_OFF_BED_THRESHOLD_KG
    }

    companion object {
        private const val MONITOR_CHANNEL_ID = "twodosumi_monitor"
        private const val ALARM_CHANNEL_ID = "twodosumi_alarm"
        private const val NOTIFICATION_ID = 2001
        private const val POLL_INTERVAL_MS = 10_000L
        private const val DEFAULT_OFF_BED_THRESHOLD_KG = 18.0
        private const val EXTRA_BASE_URL = "base_url"
        private const val EXTRA_TOKEN = "token"
        private const val EXTRA_VOLUME = "volume"
        private const val EXTRA_SOUND_ENABLED = "sound_enabled"
        private const val EXTRA_ALARM_NOTIFICATIONS_ENABLED = "alarm_notifications_enabled"
        private const val ACTION_START = "jp.twodosumi.app.START_MONITOR"
        private const val ACTION_TEST_ALARM = "jp.twodosumi.app.TEST_ALARM"
        private const val ACTION_STOP_ALARM = "jp.twodosumi.app.STOP_ALARM"
        private const val ACTION_STOP_SERVICE = "jp.twodosumi.app.STOP_SERVICE"
        private val ALARM_EVENTS = setOf("scheduled_alarm", "bed_still_occupied_realarm", "returned", "second_sleep_detected")
        private val STOP_EVENTS = setOf("alarm_dismissed", "left_bed", "monitor_done")

        fun start(
            context: Context,
            baseUrl: String,
            token: String,
            volume: Float,
            soundEnabled: Boolean,
            alarmNotificationsEnabled: Boolean,
        ) {
            val intent = Intent(context, PiMonitorService::class.java)
                .setAction(ACTION_START)
                .putExtra(EXTRA_BASE_URL, baseUrl)
                .putExtra(EXTRA_TOKEN, token)
                .putExtra(EXTRA_VOLUME, volume.coerceIn(0f, 1f))
                .putExtra(EXTRA_SOUND_ENABLED, soundEnabled)
                .putExtra(EXTRA_ALARM_NOTIFICATIONS_ENABLED, alarmNotificationsEnabled)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun testAlarm(
            context: Context,
            volume: Float,
            soundEnabled: Boolean,
            alarmNotificationsEnabled: Boolean,
        ) {
            val intent = Intent(context, PiMonitorService::class.java)
                .setAction(ACTION_TEST_ALARM)
                .putExtra(EXTRA_VOLUME, volume.coerceIn(0f, 1f))
                .putExtra(EXTRA_SOUND_ENABLED, soundEnabled)
                .putExtra(EXTRA_ALARM_NOTIFICATIONS_ENABLED, alarmNotificationsEnabled)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stopAlarm(context: Context) {
            context.startService(Intent(context, PiMonitorService::class.java).setAction(ACTION_STOP_ALARM))
        }
    }
}
