package jp.twodosumi.app

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.encodeToJsonElement

private val Context.settingsStore by preferencesDataStore(name = "twodosumi")

data class DeletedAlarm(val alarm: ScheduledAlarmDto, val index: Int)

data class UiState(
    val baseUrl: String = "http://raspberrypi.local:8080",
    val token: String = "",
    val connected: Boolean = false,
    val loading: Boolean = false,
    val busyAction: String? = null,
    val message: String? = null,
    val error: String? = null,
    val activeTab: Tab = Tab.Overview,
    val settings: SettingsDto? = null,
    val draftSettings: SettingsDto? = null,
    val status: StatusDto? = null,
    val weightHistory: List<Double> = emptyList(),
    val events: List<EventEntry> = emptyList(),
    val lastEventKey: String? = null,
    val calibrationSamples: String = "30",
    val knownKg: String = "",
    val sensorResult: SensorCheckResultDto? = null,
    val sensorRestarted: Boolean = false,
    val alarmEditorId: String? = null,
    val newAlarmDraft: ScheduledAlarmDto? = null,
    val deletedAlarm: DeletedAlarm? = null,
    val alarmSaveStatus: String? = null,
    val phoneAlarmActive: Boolean = false,
    val phoneAlarmTitle: String = "",
    val lastPhoneAlarmKey: String? = null,
    val phoneAlarmEnabled: Boolean = true,
    val phoneAlarmVolume: Float = 1.0f,
    val phoneAlarmNotificationsEnabled: Boolean = true,
)

enum class Tab(val label: String) {
    Overview("概要"),
    Alarms("アラーム"),
    Calibration("校正"),
    Settings("設定"),
}

class AppViewModel(private val appContext: Context) : ViewModel() {
    private val apiFactory = ApiFactory()
    private var pollJob: Job? = null
    private var alarmLabelJob: Job? = null
    private var saveStatusClearJob: Job? = null
    private val alarmSaveMutex = Mutex()
    private val json = Json { encodeDefaults = true }

    var uiState = androidx.compose.runtime.mutableStateOf(UiState())
        private set

    init {
        viewModelScope.launch {
            val prefs = appContext.settingsStore.data.first()
            uiState.value = uiState.value.copy(
                baseUrl = prefs[BASE_URL] ?: uiState.value.baseUrl,
                token = prefs[TOKEN] ?: "",
                phoneAlarmEnabled = prefs[PHONE_ALARM_ENABLED] ?: true,
                phoneAlarmVolume = prefs[PHONE_ALARM_VOLUME] ?: 1.0f,
                phoneAlarmNotificationsEnabled = prefs[PHONE_ALARM_NOTIFICATIONS_ENABLED] ?: true,
            )
            if (uiState.value.token.isNotBlank() && uiState.value.baseUrl.isNotBlank()) {
                connect()
            }
        }
    }

    fun updateBaseUrl(value: String) {
        uiState.value = uiState.value.copy(baseUrl = value, connected = false)
        stopPolling()
    }

    fun updateToken(value: String) {
        uiState.value = uiState.value.copy(token = value, connected = false)
        stopPolling()
    }

    fun setTab(tab: Tab) {
        uiState.value = uiState.value.copy(activeTab = tab)
    }

    fun updateCalibrationSamples(value: String) {
        uiState.value = uiState.value.copy(calibrationSamples = value.filter { it.isDigit() }.ifBlank { "1" })
    }

    fun updateKnownKg(value: String) {
        uiState.value = uiState.value.copy(knownKg = value)
    }

    fun connect() = launchWithStatus("接続中") {
        val api = api()
        val response = api.getSettings().checked()
        val settings = requireNotNull(response.settings) { "settings is missing" }
        appContext.settingsStore.edit { prefs ->
            prefs[BASE_URL] = uiState.value.baseUrl.trim()
            prefs[TOKEN] = uiState.value.token
        }
        uiState.value = uiState.value.copy(
            connected = true,
            settings = settings,
            draftSettings = settings,
            message = "接続しました",
            error = null,
        )
        startPhoneMonitor()
        loadStatus()
        startPolling()
    }

    fun refreshSettings() = launchWithStatus("設定を読み込み中") {
        loadSettingsIntoState("設定を読み込みました")
    }

    fun saveSettings() = launchWithStatus("設定を保存中") {
        val draft = requireNotNull(uiState.value.draftSettings) { "設定が読み込まれていません" }
        api().postSettings(SettingsRequest(draft)).checked()
        uiState.value = uiState.value.copy(settings = draft, message = "設定を保存しました")
        loadStatus()
    }

    fun updateDraft(transform: (SettingsDto) -> SettingsDto) {
        val current = uiState.value.draftSettings ?: return
        uiState.value = uiState.value.copy(draftSettings = transform(current))
    }

    fun hasUnsavedSettings(): Boolean {
        val committed = uiState.value.settings ?: return false
        val draft = uiState.value.draftSettings ?: return false
        return draft.withAlarmSettingsFrom(committed) != committed
    }

    fun openAlarmEditor(id: String) {
        uiState.value = uiState.value.copy(alarmEditorId = id, newAlarmDraft = null)
    }

    fun openNewAlarmEditor() {
        uiState.value = uiState.value.copy(
            alarmEditorId = NEW_ALARM_ID,
            newAlarmDraft = ScheduledAlarmDto(
                id = "alarm_${System.currentTimeMillis()}",
                time = "07:00",
                enabled = true,
                label = "",
                weekdays = (0..6).toList(),
            ),
        )
    }

    fun closeAlarmEditor() {
        uiState.value = uiState.value.copy(alarmEditorId = null, newAlarmDraft = null)
    }

    fun updateNewAlarm(transform: (ScheduledAlarmDto) -> ScheduledAlarmDto) {
        val current = uiState.value.newAlarmDraft ?: return
        uiState.value = uiState.value.copy(newAlarmDraft = transform(current))
    }

    fun createAlarm() {
        val alarm = uiState.value.newAlarmDraft ?: return
        mutateAlarmSettings { it.copy(scheduledAlarms = it.scheduledAlarms + alarm) }
        persistAlarmSettings(onSuccess = {
            uiState.value = uiState.value.copy(alarmEditorId = null, newAlarmDraft = null)
        })
    }

    fun updateAlarm(id: String, transform: (ScheduledAlarmDto) -> ScheduledAlarmDto) {
        mutateAlarmSettings { settings ->
            settings.copy(
                scheduledAlarms = settings.scheduledAlarms.map { alarm ->
                    if (alarm.id == id) transform(alarm) else alarm
                }
            )
        }
        persistAlarmSettings()
    }

    fun updateAlarmLabel(id: String, label: String) {
        mutateAlarmSettings { settings ->
            settings.copy(
                scheduledAlarms = settings.scheduledAlarms.map { alarm ->
                    if (alarm.id == id) alarm.copy(label = label) else alarm
                }
            )
        }
        alarmLabelJob?.cancel()
        alarmLabelJob = viewModelScope.launch {
            delay(500)
            persistAlarmSettings()
        }
    }

    fun setScheduledAlarmEnabled(enabled: Boolean) {
        mutateAlarmSettings { it.copy(scheduledAlarmEnabled = enabled) }
        persistAlarmSettings()
    }

    fun setWakeMissionEnabled(enabled: Boolean) {
        mutateAlarmSettings { it.copy(wakeMissionEnabled = enabled) }
        persistAlarmSettings()
    }

    fun setBedRecheckMinutes(value: Double) {
        mutateAlarmSettings { it.copy(bedRecheckMinutes = value) }
        persistAlarmSettings()
    }

    fun setWakeMissionRequiredSeconds(value: Double) {
        mutateAlarmSettings { it.copy(wakeMissionRequiredOffBedSec = value) }
        persistAlarmSettings()
    }

    fun setSecondSleepConfirmSeconds(value: Double) {
        mutateAlarmSettings { it.copy(confirmSec = value.coerceAtLeast(10.0)) }
        persistAlarmSettings()
    }

    fun deleteAlarm(id: String) {
        val settings = uiState.value.draftSettings ?: return
        val index = settings.scheduledAlarms.indexOfFirst { it.id == id }
        if (index < 0) return
        val deleted = DeletedAlarm(settings.scheduledAlarms[index], index)
        mutateAlarmSettings {
            it.copy(scheduledAlarms = it.scheduledAlarms.filterNot { alarm -> alarm.id == id })
        }
        uiState.value = uiState.value.copy(alarmEditorId = null)
        persistAlarmSettings(onSuccess = {
            uiState.value = uiState.value.copy(deletedAlarm = deleted)
        })
    }

    fun undoDeleteAlarm() {
        val deleted = uiState.value.deletedAlarm ?: return
        mutateAlarmSettings { settings ->
            val alarms = settings.scheduledAlarms.toMutableList()
            alarms.add(deleted.index.coerceIn(0, alarms.size), deleted.alarm)
            settings.copy(scheduledAlarms = alarms)
        }
        uiState.value = uiState.value.copy(deletedAlarm = null)
        persistAlarmSettings()
    }

    fun clearDeletedAlarm() {
        uiState.value = uiState.value.copy(deletedAlarm = null)
    }

    fun startRun() = launchWithStatus("開始中") {
        api().startRun().checked()
        startPhoneMonitor()
        uiState.value = uiState.value.copy(message = "検知を開始しました")
        loadStatus()
    }

    fun stopRun() = launchWithStatus("停止中") {
        api().stopRun().checked()
        uiState.value = uiState.value.copy(message = "検知を停止しました")
        loadStatus()
    }

    fun loadStatus() = viewModelScope.launch {
        runCatching {
            val response = api().getStatus().checked()
            requireNotNull(response.status) { "status is missing" }
        }.onSuccess { status ->
            val weightHistory = status.smoothedWeightKg
                ?.let { (uiState.value.weightHistory + it).takeLast(60) }
                ?: uiState.value.weightHistory
            val eventUpdate = trackEvent(status)
            val phoneAlarm = phoneAlarmUpdate(status)
            uiState.value = uiState.value.copy(
                status = status,
                weightHistory = weightHistory,
                events = eventUpdate.first,
                lastEventKey = eventUpdate.second,
                phoneAlarmActive = phoneAlarm.active,
                phoneAlarmTitle = phoneAlarm.title,
                lastPhoneAlarmKey = phoneAlarm.key,
                error = null,
            )
        }.onFailure { exc ->
            uiState.value = uiState.value.copy(error = exc.displayMessage())
        }
    }

    fun checkSensor() = launchWithStatus("センサー確認中") {
        val response = api().checkSensor(SensorCheckRequest(samples = sampleCount())).checked()
        uiState.value = uiState.value.copy(
            sensorResult = requireNotNull(response.sensor) { "sensor result is missing" },
            sensorRestarted = response.restarted,
            message = if (response.sensor.ok) "センサー確認: OK" else "センサー確認: NG",
        )
    }

    fun calibrateZero() = launchWithStatus("ゼロ校正中") {
        val response = api().calibrateZero(SampleRequest(sampleCount())).checked()
        loadSettingsIntoState("ZERO_OFFSET saved: ${response.zeroOffset?.format(3) ?: "-"}")
    }

    fun calibrateScale() = launchWithStatus("重量校正中") {
        val known = uiState.value.knownKg.toDoubleOrNull()
        require(known != null && known > 0.0) { "既知重量 kg を入力してください" }
        val response = api().calibrateScale(ScaleRequest(samples = sampleCount(), knownKg = known)).checked()
        loadSettingsIntoState("SCALE_FACTOR saved: ${response.scaleFactor?.format(6) ?: "-"}")
    }

    fun testWebhook() = launchWithStatus("Webhookテスト中") {
        api().testWebhook().checked()
        uiState.value = uiState.value.copy(message = "Webhookテストを送信しました")
    }

    fun dismissPhoneAlarm() {
        PiMonitorService.stopAlarm(appContext)
        uiState.value = uiState.value.copy(phoneAlarmActive = false, phoneAlarmTitle = "")
    }

    fun setPhoneAlarmEnabled(enabled: Boolean) {
        uiState.value = uiState.value.copy(phoneAlarmEnabled = enabled)
        persistPhoneAlarmSettings()
    }

    fun setPhoneAlarmVolume(value: Float) {
        uiState.value = uiState.value.copy(phoneAlarmVolume = value.coerceIn(0f, 1f))
        persistPhoneAlarmSettings()
    }

    fun setPhoneAlarmNotificationsEnabled(enabled: Boolean) {
        uiState.value = uiState.value.copy(phoneAlarmNotificationsEnabled = enabled)
        persistPhoneAlarmSettings()
    }

    fun testPhoneAlarm() {
        PiMonitorService.testAlarm(
            appContext,
            volume = uiState.value.phoneAlarmVolume,
            soundEnabled = uiState.value.phoneAlarmEnabled,
            alarmNotificationsEnabled = uiState.value.phoneAlarmNotificationsEnabled,
        )
        uiState.value = uiState.value.copy(
            phoneAlarmActive = true,
            phoneAlarmTitle = "テストアラーム",
            message = "スマホアラームをテスト再生しました",
        )
    }

    fun clearMessage() {
        uiState.value = uiState.value.copy(message = null, error = null)
    }

    private fun api(): TwodosumiApi {
        val state = uiState.value
        require(state.baseUrl.isNotBlank()) { "接続先URLを入力してください" }
        require(state.token.isNotBlank()) { "Web UI Tokenを入力してください" }
        return apiFactory.create(state.baseUrl, state.token)
    }

    private fun sampleCount(): Int = uiState.value.calibrationSamples.toIntOrNull()?.coerceAtLeast(1) ?: 1

    private fun startPhoneMonitor() {
        PiMonitorService.start(
            appContext,
            uiState.value.baseUrl,
            uiState.value.token,
            volume = uiState.value.phoneAlarmVolume,
            soundEnabled = uiState.value.phoneAlarmEnabled,
            alarmNotificationsEnabled = uiState.value.phoneAlarmNotificationsEnabled,
        )
    }

    private fun persistPhoneAlarmSettings() {
        val state = uiState.value
        viewModelScope.launch {
            appContext.settingsStore.edit { prefs ->
                prefs[PHONE_ALARM_ENABLED] = state.phoneAlarmEnabled
                prefs[PHONE_ALARM_VOLUME] = state.phoneAlarmVolume
                prefs[PHONE_ALARM_NOTIFICATIONS_ENABLED] = state.phoneAlarmNotificationsEnabled
            }
        }
        if (state.connected && state.baseUrl.isNotBlank() && state.token.isNotBlank()) {
            startPhoneMonitor()
        }
    }

    private fun mutateAlarmSettings(transform: (SettingsDto) -> SettingsDto) {
        val current = uiState.value.draftSettings ?: return
        saveStatusClearJob?.cancel()
        uiState.value = uiState.value.copy(
            draftSettings = transform(current),
            alarmSaveStatus = "保存中",
            error = null,
        )
    }

    private fun persistAlarmSettings(onSuccess: (() -> Unit)? = null) {
        viewModelScope.launch {
            alarmSaveMutex.withLock {
                val snapshot = uiState.value.draftSettings ?: return@withLock
                runCatching {
                    api().postPartialSettings(PartialSettingsRequest(alarmPayload(snapshot))).checked()
                }.onSuccess {
                    val committed = (uiState.value.settings ?: snapshot).withAlarmSettingsFrom(snapshot)
                    uiState.value = uiState.value.copy(settings = committed, alarmSaveStatus = "保存済み")
                    saveStatusClearJob?.cancel()
                    saveStatusClearJob = viewModelScope.launch {
                        delay(2_500)
                        if (uiState.value.alarmSaveStatus == "保存済み") {
                            uiState.value = uiState.value.copy(alarmSaveStatus = null)
                        }
                    }
                    onSuccess?.invoke()
                }.onFailure { exc ->
                    saveStatusClearJob?.cancel()
                    val committed = uiState.value.settings
                    uiState.value = uiState.value.copy(
                        draftSettings = if (committed == null) uiState.value.draftSettings else {
                            uiState.value.draftSettings?.withAlarmSettingsFrom(committed)
                        },
                        alarmSaveStatus = "保存失敗",
                        error = exc.displayMessage(),
                    )
                }
            }
        }
    }

    private fun alarmPayload(settings: SettingsDto) = mapOf(
        "scheduled_alarm_enabled" to JsonPrimitive(settings.scheduledAlarmEnabled),
        "scheduled_alarms" to json.encodeToJsonElement(settings.scheduledAlarms),
        "bed_recheck_minutes" to JsonPrimitive(settings.bedRecheckMinutes),
        "wake_mission_enabled" to JsonPrimitive(settings.wakeMissionEnabled),
        "wake_mission_required_off_bed_sec" to JsonPrimitive(settings.wakeMissionRequiredOffBedSec),
        "confirm_sec" to JsonPrimitive(settings.confirmSec),
    )

    private fun SettingsDto.withAlarmSettingsFrom(source: SettingsDto) = copy(
        scheduledAlarmEnabled = source.scheduledAlarmEnabled,
        scheduledAlarms = source.scheduledAlarms,
        bedRecheckMinutes = source.bedRecheckMinutes,
        wakeMissionEnabled = source.wakeMissionEnabled,
        wakeMissionRequiredOffBedSec = source.wakeMissionRequiredOffBedSec,
        confirmSec = source.confirmSec,
    )

    private fun launchWithStatus(action: String, block: suspend () -> Unit) {
        viewModelScope.launch {
            uiState.value = uiState.value.copy(loading = true, busyAction = action, error = null, message = null)
            runCatching { block() }
                .onFailure { exc -> uiState.value = uiState.value.copy(error = exc.displayMessage()) }
            uiState.value = uiState.value.copy(loading = false, busyAction = null)
        }
    }

    private suspend fun loadSettingsIntoState(message: String) {
        val response = api().getSettings().checked()
        val settings = requireNotNull(response.settings) { "settings is missing" }
        uiState.value = uiState.value.copy(settings = settings, draftSettings = settings, message = message)
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            while (true) {
                delay(3_000)
                loadStatus()
            }
        }
    }

    private fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    private fun trackEvent(status: StatusDto): Pair<List<EventEntry>, String?> {
        val sig = "${status.state}|${status.event}"
        if (sig == "|" || sig == uiState.value.lastEventKey) {
            return uiState.value.events to uiState.value.lastEventKey
        }
        val meta = StateLabels[status.state]
        val entry = EventEntry(
            label = meta?.label ?: (status.event.ifBlank { status.state.ifBlank { "更新" } }),
            detail = status.event,
            tone = meta?.tone ?: Tone.Idle,
            time = shortTime(status.timestamp),
        )
        return (listOf(entry) + uiState.value.events).take(20) to sig
    }

    private data class PhoneAlarmState(val active: Boolean, val title: String, val key: String?)

    private fun phoneAlarmUpdate(status: StatusDto): PhoneAlarmState {
        val current = uiState.value
        val pendingRechecks = status.pendingRechecks.orEmpty()
        val settings = current.settings ?: current.draftSettings
        val offBed = isOffBed(status, settings)
        val returnedStateKey = "state|RETURNED"
        val currentKey = if (status.state != "RETURNED" && current.lastPhoneAlarmKey == returnedStateKey) {
            null
        } else {
            current.lastPhoneAlarmKey
        }
        if (
            offBed ||
            status.event in PHONE_ALARM_STOP_EVENTS ||
            (
                current.phoneAlarmActive &&
                    current.phoneAlarmTitle != "二度寝検知" &&
                    pendingRechecks.isEmpty() &&
                    status.event !in PHONE_ALARM_EVENTS
                )
        ) {
            return PhoneAlarmState(active = false, title = "", key = currentKey)
        }

        val sig = "${status.timestamp.orEmpty()}|${status.event}"
        if (status.event in PHONE_ALARM_EVENTS && sig != currentKey) {
            return PhoneAlarmState(active = true, title = phoneAlarmTitle(status.event), key = sig)
        }
        if (status.state == "RETURNED" && currentKey != returnedStateKey) {
            return PhoneAlarmState(active = true, title = "再入床", key = returnedStateKey)
        }
        if (pendingRechecks.isNotEmpty()) {
            val key = pendingRechecks.joinToString("|") { "${it.time}|${it.label}|${it.realarmCount}" }
            if (key != currentKey) {
                return PhoneAlarmState(active = true, title = "起床アラーム", key = key)
            }
        }

        return PhoneAlarmState(
            active = current.phoneAlarmActive,
            title = current.phoneAlarmTitle,
            key = currentKey,
        )
    }

    private fun phoneAlarmTitle(event: String): String = when (event) {
        "scheduled_alarm" -> "起床アラーム"
        "bed_still_occupied_realarm" -> "再アラーム"
        "returned" -> "再入床"
        "second_sleep_detected" -> "二度寝検知"
        else -> "2dosumiアラーム"
    }

    private fun isOffBed(status: StatusDto, settings: SettingsDto?): Boolean {
        val weight = status.smoothedWeightKg ?: status.weightKg ?: return false
        val threshold = (settings?.personWeightKg ?: 60.0) * (settings?.exitRatio ?: 0.3)
        return weight < threshold
    }

    private fun shortTime(timestamp: String?): String {
        return formatLocalTime(timestamp, "HH:mm")
    }

    private fun Double.format(digits: Int): String = "%.${digits}f".format(this)

    private fun Throwable.displayMessage(): String = message ?: javaClass.simpleName

    private fun BasicResponse.checked(): BasicResponse {
        if (!ok) throw IllegalStateException(error ?: "request failed")
        return this
    }

    private fun SettingsResponse.checked(): SettingsResponse {
        if (!ok) throw IllegalStateException(error ?: "request failed")
        return this
    }

    private fun StatusResponse.checked(): StatusResponse {
        if (!ok) throw IllegalStateException(error ?: "request failed")
        return this
    }

    private fun ZeroCalibrationResponse.checked(): ZeroCalibrationResponse {
        if (!ok) throw IllegalStateException(error ?: "request failed")
        return this
    }

    private fun ScaleCalibrationResponse.checked(): ScaleCalibrationResponse {
        if (!ok) throw IllegalStateException(error ?: "request failed")
        return this
    }

    private fun SensorCheckResponse.checked(): SensorCheckResponse {
        if (!ok) throw IllegalStateException(error ?: "request failed")
        return this
    }

    companion object {
        private val BASE_URL = stringPreferencesKey("base_url")
        private val TOKEN = stringPreferencesKey("token")
        private val PHONE_ALARM_ENABLED = booleanPreferencesKey("phone_alarm_enabled")
        private val PHONE_ALARM_VOLUME = floatPreferencesKey("phone_alarm_volume")
        private val PHONE_ALARM_NOTIFICATIONS_ENABLED = booleanPreferencesKey("phone_alarm_notifications_enabled")
        const val NEW_ALARM_ID = "__new_alarm__"
        private val PHONE_ALARM_EVENTS = setOf(
            "scheduled_alarm",
            "bed_still_occupied_realarm",
            "returned",
            "second_sleep_detected",
        )
        private val PHONE_ALARM_STOP_EVENTS = setOf(
            "alarm_dismissed",
            "left_bed",
            "monitor_done",
        )
    }
}
