@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package jp.twodosumi.app

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.AlarmClock
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Alarm
import androidx.compose.material.icons.outlined.AddAlarm
import androidx.compose.material.icons.outlined.Build
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Save
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import java.util.Calendar
import kotlin.math.max

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermission()
        setContent {
            TwodosumiTheme {
                TwodosumiApp()
            }
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return
        requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001)
    }
}

@Composable
private fun TwodosumiTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = androidx.compose.material3.lightColorScheme(
            primary = Color(0xFF007AFF),
            secondary = Color(0xFF34C759),
            error = Color(0xFFFF3B30),
            surface = Color(0xFFFFFFFF),
            background = Color(0xFFF2F2F7),
        ),
        content = content,
    )
}

@Composable
private fun TwodosumiApp() {
    val context = LocalContext.current.applicationContext
    val vm: AppViewModel = viewModel(factory = object : ViewModelProvider.Factory {
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            @Suppress("UNCHECKED_CAST")
            return AppViewModel(context) as T
        }
    })
    val state by vm.uiState
    val snackbar = remember { SnackbarHostState() }
    val snackbarText = state.error ?: state.message

    LaunchedEffect(snackbarText) {
        if (!snackbarText.isNullOrBlank()) {
            snackbar.showSnackbar(snackbarText)
            vm.clearMessage()
        }
    }
    LaunchedEffect(state.deletedAlarm) {
        if (state.deletedAlarm != null) {
            val result = snackbar.showSnackbar(
                message = "アラームを削除しました",
                actionLabel = "元に戻す",
            )
            if (result == SnackbarResult.ActionPerformed) vm.undoDeleteAlarm() else vm.clearDeletedAlarm()
        }
    }
    if (state.phoneAlarmActive) {
        PhoneAlarmDialog(
            title = state.phoneAlarmTitle.ifBlank { "2dosumiアラーム" },
            onDismiss = vm::dismissPhoneAlarm,
        )
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar {
                Tab.entries.forEach { tab ->
                    NavigationBarItem(
                        selected = state.activeTab == tab,
                        onClick = { vm.setTab(tab) },
                        icon = { Icon(tab.icon(), contentDescription = tab.label) },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        Surface(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            color = MaterialTheme.colorScheme.background,
        ) {
            when (state.activeTab) {
                Tab.Overview -> OverviewScreen(state, vm)
                Tab.Alarms -> AlarmsScreen(state, vm)
                Tab.Calibration -> CalibrationScreen(state, vm)
                Tab.Settings -> SettingsScreen(state, vm)
            }
        }
    }
}

@Composable
private fun PhoneAlarmDialog(title: String, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = {},
        title = { Text(title) },
        text = { Text("スマホでアラームを鳴らしています。") },
        confirmButton = {
            Button(onClick = onDismiss) {
                Text("停止")
            }
        },
    )
}

private fun Tab.icon(): ImageVector = when (this) {
    Tab.Overview -> Icons.Outlined.Home
    Tab.Alarms -> Icons.Outlined.Alarm
    Tab.Calibration -> Icons.Outlined.Build
    Tab.Settings -> Icons.Outlined.Settings
}

@Composable
private fun OverviewScreen(state: UiState, vm: AppViewModel) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { CompactHeader(state) }
        if (!state.connected) item { ConnectCard(state, vm) }
        item { StatusHero(state, vm) }
        item { AlarmSummary(state) }
        item { StatusDetails(state) }
        item { EventTimeline(state.events) }
    }
}

@Composable
private fun CompactHeader(state: UiState) {
    Row(
        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("2dosumi", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            CompactStatus(if (state.connected) "接続済" else "未接続", if (state.connected) Tone.Done else Tone.Idle)
            CompactStatus(if (isRunning(state.status)) "稼働中" else "停止中", if (isRunning(state.status)) Tone.Sleep else Tone.Idle)
        }
    }
}

@Composable
private fun CompactStatus(label: String, tone: Tone) {
    Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
        ToneDot(tone)
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ConnectCard(state: UiState, vm: AppViewModel) {
    SectionCard(title = "接続") {
        OutlinedTextField(
            value = state.baseUrl,
            onValueChange = vm::updateBaseUrl,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Pi Web UI URL") },
            placeholder = { Text("http://raspberrypi.local:8080") },
            singleLine = true,
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = state.token,
            onValueChange = vm::updateToken,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Web UI Token") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
        )
        if (state.baseUrl.startsWith("http://")) {
            Spacer(Modifier.height(6.dp))
            Text("HTTP接続です。Tailscale Serve等でHTTPSが使える場合はHTTPSを推奨します。", color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = vm::connect,
            enabled = !state.loading,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(state.busyAction ?: "保存して接続")
        }
    }
}

@Composable
private fun StatusHero(state: UiState, vm: AppViewModel) {
    val status = state.status
    val settings = state.settings ?: state.draftSettings
    val meta = StateLabels[status?.state.orEmpty()]
    val presence = presenceLabel(status?.smoothedWeightKg ?: status?.weightKg, settings)
    SectionCard(title = "概要") {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ToneChip(meta?.label ?: status?.state?.ifBlank { "未取得" } ?: "未取得", meta?.tone ?: Tone.Idle)
            Spacer(Modifier.width(8.dp))
            Text(
                status?.timestamp?.let { "${formatLocalTime(it, "HH:mm:ss")} 更新" } ?: "更新待ち",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.weight(1f))
            IconButton(onClick = vm::loadStatus) {
                Icon(Icons.Outlined.Refresh, contentDescription = "状態更新")
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            presence,
            style = MaterialTheme.typography.displaySmall,
            fontWeight = FontWeight.Bold,
        )
        Text(
            status?.smoothedWeightKg?.let { "推定 %.1f kg 相当".format(it) } ?: "検知開始後に判定します",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Sparkline(state.weightHistory)
        MissionProgress(status?.pendingRechecks.orEmpty())
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = vm::startRun, enabled = !state.loading, modifier = Modifier.weight(1f)) {
                Text("検知開始")
            }
            OutlinedButton(onClick = vm::stopRun, enabled = !state.loading, modifier = Modifier.weight(1f)) {
                Text("検知停止")
            }
        }
    }
}

@Composable
private fun AlarmSummary(state: UiState) {
    val settings = state.draftSettings ?: state.settings
    val enabled = settings?.scheduledAlarms.orEmpty().filter { it.enabled }
    val featured = state.status?.nextScheduledAlarm ?: enabled.firstOrNull()
    val others = enabled.filterNot { it.id == featured?.id }.take(3)
    SectionCard(title = "次のアラーム") {
        if (featured == null) {
            Text("次のアラームは未設定です", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(featured.time, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(featured.label.ifBlank { "アラーム" }, fontWeight = FontWeight.SemiBold)
                    Text(formatWeekdaySummary(featured.weekdays), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        if (others.isNotEmpty()) {
            HorizontalDivider(Modifier.padding(vertical = 10.dp))
            others.forEach { alarm ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(alarm.time, fontWeight = FontWeight.Bold, modifier = Modifier.width(64.dp))
                    Text(
                        "${alarm.label.ifBlank { "アラーム" }}  ${formatWeekdaySummary(alarm.weekdays)}",
                        modifier = Modifier.weight(1f),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun StatusDetails(state: UiState) {
    val status = state.status
    val settings = state.settings ?: state.draftSettings
    SectionCard(title = "状態") {
        MetricGrid(
            listOf(
                "在床判定" to presenceLabel(status?.smoothedWeightKg ?: status?.weightKg, settings),
                "状態" to (StateLabels[status?.state.orEmpty()]?.label ?: status?.state.orEmpty().ifBlank { "-" }),
                "イベント" to status?.event.orEmpty().ifBlank { "-" },
                "推定値" to (status?.smoothedWeightKg?.let { "%.2f kg相当".format(it) } ?: "-"),
                "プロセス" to if (isRunning(status)) "稼働中" else "停止中",
                "次アラーム" to (formatAlarm(status?.nextScheduledAlarm) ?: "-"),
                "再確認" to formatRechecks(status?.pendingRechecks.orEmpty()),
            )
        )
    }
}

@Composable
private fun EventTimeline(events: List<EventEntry>) {
    SectionCard(title = "最近のできごと") {
        if (events.isEmpty()) {
            Text("状態の変化がここに記録されます。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            events.forEach { entry ->
                Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    ToneDot(entry.tone)
                    Spacer(Modifier.width(10.dp))
                    Text(entry.label, modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                    Text(entry.time, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun AlarmsScreen(state: UiState, vm: AppViewModel) {
    val settings = state.draftSettings ?: state.settings
    val context = LocalContext.current
    val editorId = state.alarmEditorId
    if (editorId != null) {
        val alarm = if (editorId == AppViewModel.NEW_ALARM_ID) {
            state.newAlarmDraft
        } else {
            settings?.scheduledAlarms?.firstOrNull { it.id == editorId }
        }
        if (alarm != null) {
            AlarmEditorScreen(
                alarm = alarm,
                isNew = editorId == AppViewModel.NEW_ALARM_ID,
                saveStatus = state.alarmSaveStatus,
                loading = state.loading,
                onBack = vm::closeAlarmEditor,
                onChange = { transform ->
                    if (editorId == AppViewModel.NEW_ALARM_ID) vm.updateNewAlarm(transform)
                    else vm.updateAlarm(editorId, transform)
                },
                onLabelChange = { label ->
                    if (editorId == AppViewModel.NEW_ALARM_ID) {
                        vm.updateNewAlarm { it.copy(label = label) }
                    } else {
                        vm.updateAlarmLabel(editorId, label)
                    }
                },
                onCreate = vm::createAlarm,
                onDelete = { vm.deleteAlarm(editorId) },
                onAddToClock = { addToClockApp(context, alarm) },
            )
            return
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { CompactHeader(state) }
        item {
            SectionCard(title = "時刻アラーム") {
                ToggleRow(
                    title = "有効",
                    description = "登録時刻にベッド上なら鳴らす",
                    checked = settings?.scheduledAlarmEnabled == true,
                    onCheckedChange = vm::setScheduledAlarmEnabled,
                )
                SaveStatusLabel(state.alarmSaveStatus)
            }
        }
        item {
            SectionCard(title = "登録済み") {
                if (settings?.scheduledAlarms.isNullOrEmpty()) {
                    Text("アラームはありません", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                val alarms = settings?.scheduledAlarms.orEmpty()
                alarms.forEachIndexed { index, alarm ->
                    AlarmListRow(
                        alarm = alarm,
                        onEnabledChange = { enabled -> vm.updateAlarm(alarm.id) { it.copy(enabled = enabled) } },
                        onEdit = { vm.openAlarmEditor(alarm.id) },
                        onAddToClock = { addToClockApp(context, alarm) },
                    )
                    if (index < alarms.lastIndex) {
                        HorizontalDivider(Modifier.padding(vertical = 4.dp))
                    }
                }
                if (alarms.isNotEmpty()) Spacer(Modifier.height(8.dp))
                OutlinedButton(onClick = vm::openNewAlarmEditor, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Outlined.Add, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("アラームを追加")
                }
            }
        }
        item {
            SectionCard(title = "起床ミッション") {
                ToggleRow(
                    title = "有効",
                    description = "離床を確認するまで再アラーム",
                    checked = settings?.wakeMissionEnabled == true,
                    onCheckedChange = vm::setWakeMissionEnabled,
                )
                settings?.let {
                    RecheckIntervalControl(it.bedRecheckMinutes, vm::setBedRecheckMinutes)
                    NumberField("離床確認 秒", it.wakeMissionRequiredOffBedSec, vm::setWakeMissionRequiredSeconds)
                }
            }
        }
        item {
            SectionCard(title = "二度寝検知") {
                settings?.let {
                    SecondSleepConfirmControl(it.confirmSec, vm::setSecondSleepConfirmSeconds)
                    SaveStatusLabel(state.alarmSaveStatus)
                }
            }
        }
    }
}

@Composable
private fun RecheckIntervalControl(value: Double, onChange: (Double) -> Unit) {
    Text("再確認 ${value.cleanString()} 分", fontWeight = FontWeight.SemiBold)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        listOf(3.0, 5.0, 10.0, 15.0).forEach { minutes ->
            FilterChip(
                selected = value == minutes,
                onClick = { onChange(minutes) },
                modifier = Modifier.weight(1f),
                label = { Text("${minutes.toInt()}分") },
            )
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { onChange((value - 1.0).coerceAtLeast(1.0)) },
            modifier = Modifier.weight(1f),
        ) {
            Text("-1分")
        }
        OutlinedButton(
            onClick = { onChange(value + 1.0) },
            modifier = Modifier.weight(1f),
        ) {
            Text("+1分")
        }
    }
}

@Composable
private fun SecondSleepConfirmControl(value: Double, onChange: (Double) -> Unit) {
    Text("二度寝確定 ${value.cleanString()} 秒", fontWeight = FontWeight.SemiBold)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        listOf(30.0, 60.0, 120.0, 180.0).forEach { seconds ->
            FilterChip(
                selected = value == seconds,
                onClick = { onChange(seconds) },
                modifier = Modifier.weight(1f),
                label = { Text("${seconds.toInt()}秒") },
            )
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { onChange((value - 10.0).coerceAtLeast(10.0)) },
            modifier = Modifier.weight(1f),
        ) {
            Text("-10秒")
        }
        OutlinedButton(
            onClick = { onChange(value + 10.0) },
            modifier = Modifier.weight(1f),
        ) {
            Text("+10秒")
        }
    }
}

@Composable
private fun AlarmListRow(
    alarm: ScheduledAlarmDto,
    onEnabledChange: (Boolean) -> Unit,
    onEdit: () -> Unit,
    onAddToClock: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .alpha(if (alarm.enabled) 1f else 0.45f)
            .clickable(onClickLabel = "アラームを編集", onClick = onEdit)
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(alarm.time, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
            Text(alarm.label.ifBlank { "アラーム" }, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                formatWeekdaySummary(alarm.weekdays),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        IconButton(onClick = onAddToClock, enabled = alarm.enabled) {
            Icon(Icons.Outlined.AddAlarm, contentDescription = "時計アプリへ登録")
        }
        Switch(checked = alarm.enabled, onCheckedChange = onEnabledChange)
    }
}

@Composable
private fun AlarmEditorScreen(
    alarm: ScheduledAlarmDto,
    isNew: Boolean,
    saveStatus: String?,
    loading: Boolean,
    onBack: () -> Unit,
    onChange: ((ScheduledAlarmDto) -> ScheduledAlarmDto) -> Unit,
    onLabelChange: (String) -> Unit,
    onCreate: () -> Unit,
    onDelete: () -> Unit,
    onAddToClock: () -> Unit,
) {
    var showTimePicker by remember(alarm.id) { mutableStateOf(false) }
    val timeParts = alarm.time.split(":")
    val initialHour = timeParts.getOrNull(0)?.toIntOrNull()?.coerceIn(0, 23) ?: 7
    val initialMinute = timeParts.getOrNull(1)?.toIntOrNull()?.coerceIn(0, 59) ?: 0
    BackHandler(onBack = onBack)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "戻る")
                }
                Text(
                    if (isNew) "アラームを追加" else "アラームを編集",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                if (!isNew) {
                    SaveStatusLabel(saveStatus)
                }
            }
        }
        item {
            SectionCard {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(onClickLabel = "時刻を変更") { showTimePicker = true }
                        .padding(vertical = 12.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        alarm.time,
                        style = MaterialTheme.typography.displayLarge,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        "タップして時刻を変更",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                HorizontalDivider(Modifier.padding(vertical = 12.dp))
                ToggleRow("有効", checked = alarm.enabled) {
                    onChange { current -> current.copy(enabled = it) }
                }
                TextFieldRow("ラベル", alarm.label, onChange = onLabelChange)
                Text("曜日", fontWeight = FontWeight.SemiBold)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    listOf(
                        "毎日" to (0..6).toList(),
                        "平日" to (0..4).toList(),
                        "週末" to listOf(5, 6),
                    ).forEach { (label, days) ->
                        TextButton(
                            onClick = { onChange { current -> current.copy(weekdays = days) } },
                            modifier = Modifier.weight(1f),
                        ) {
                            Text(label)
                        }
                    }
                }
                WeekdayToggleRow(alarm.weekdays) { day ->
                    onChange { current ->
                        val days = if (current.weekdays.contains(day)) {
                            current.weekdays - day
                        } else {
                            (current.weekdays + day).sorted()
                        }
                        current.copy(weekdays = days)
                    }
                }
                Text(
                    formatWeekdaySummary(alarm.weekdays),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
        item {
            if (isNew) {
                Button(onClick = onCreate, enabled = !loading, modifier = Modifier.fillMaxWidth()) {
                    Text("追加")
                }
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick = onAddToClock, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Outlined.AddAlarm, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("時計へ登録")
                    }
                    OutlinedButton(
                        onClick = onDelete,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.error),
                    ) {
                        Icon(Icons.Outlined.Delete, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("削除")
                    }
                }
            }
        }
    }

    if (showTimePicker) {
        val pickerState = rememberTimePickerState(
            initialHour = initialHour,
            initialMinute = initialMinute,
            is24Hour = true,
        )
        AlertDialog(
            onDismissRequest = { showTimePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    val time = "%02d:%02d".format(pickerState.hour, pickerState.minute)
                    onChange { it.copy(time = time) }
                    showTimePicker = false
                }) { Text("決定") }
            },
            dismissButton = {
                TextButton(onClick = { showTimePicker = false }) { Text("キャンセル") }
            },
            text = { TimePicker(state = pickerState) },
        )
    }
}

private fun addToClockApp(context: Context, alarm: ScheduledAlarmDto) {
    val parts = alarm.time.split(":")
    val hour = parts.getOrNull(0)?.toIntOrNull()
    val minute = parts.getOrNull(1)?.toIntOrNull()
    if (hour !in 0..23 || minute !in 0..59) {
        Toast.makeText(context, "時刻はHH:mm形式で入力してください", Toast.LENGTH_SHORT).show()
        return
    }

    val calendarDays = alarm.weekdays.map { day ->
        when (day) {
            0 -> Calendar.MONDAY
            1 -> Calendar.TUESDAY
            2 -> Calendar.WEDNESDAY
            3 -> Calendar.THURSDAY
            4 -> Calendar.FRIDAY
            5 -> Calendar.SATURDAY
            else -> Calendar.SUNDAY
        }
    }
    val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
        putExtra(AlarmClock.EXTRA_HOUR, hour)
        putExtra(AlarmClock.EXTRA_MINUTES, minute)
        putExtra(AlarmClock.EXTRA_MESSAGE, alarm.label.ifBlank { "2dosumi" })
        putExtra(AlarmClock.EXTRA_SKIP_UI, false)
        if (calendarDays.isNotEmpty()) {
            putIntegerArrayListExtra(AlarmClock.EXTRA_DAYS, ArrayList(calendarDays))
        }
    }
    try {
        context.startActivity(intent)
    } catch (_: ActivityNotFoundException) {
        Toast.makeText(context, "対応する時計アプリがありません", Toast.LENGTH_SHORT).show()
    }
}

@Composable
private fun CalibrationScreen(state: UiState, vm: AppViewModel) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { CompactHeader(state) }
        item {
            SectionCard {
                Text(
                    "何も載せずにゼロ校正 → 既知重量を載せて重量校正",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = state.calibrationSamples,
                    onValueChange = vm::updateCalibrationSamples,
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("サンプル数") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = state.knownKg,
                    onValueChange = vm::updateKnownKg,
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("既知重量 kg") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                )
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = vm::calibrateZero, enabled = !state.loading, modifier = Modifier.weight(1f)) { Text("ゼロ校正") }
                    Button(
                        onClick = vm::calibrateScale,
                        enabled = !state.loading && (state.knownKg.toDoubleOrNull()?.let { it > 0 } == true),
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("重量校正")
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedButton(onClick = vm::checkSensor, enabled = !state.loading, modifier = Modifier.fillMaxWidth()) {
                    Text("センサー確認")
                }
            }
        }
        if (state.sensorResult != null) {
            item { SensorResultCard(state.sensorResult, state.sensorRestarted) }
        }
    }
}

@Composable
private fun SensorResultCard(sensor: SensorCheckResultDto?, restarted: Boolean) {
    SectionCard(title = "センサー確認結果") {
        if (sensor == null) return@SectionCard
        ToneChip(if (sensor.ok) "OK" else "NG", if (sensor.ok) Tone.Done else Tone.Alert)
        Spacer(Modifier.height(8.dp))
        Text(sensor.message.ifBlank { "-" })
        MetricGrid(
            listOf(
                "reader" to sensor.reader,
                "samples" to "${sensor.samplesRead}/${sensor.samplesRequested}",
                "duration" to "%.2f sec".format(sensor.durationSec),
                "raw" to listOfNotNull(sensor.rawMin, sensor.rawMax, sensor.rawMedian, sensor.rawSpan)
                    .takeIf { it.isNotEmpty() }
                    ?.joinToString(" / ") { "%.3f".format(it) }
                    .orEmpty().ifBlank { "-" },
                "weight median" to (sensor.weightMedianKg?.let { "%.3f kg".format(it) } ?: "-"),
            )
        )
        sensor.warnings.forEach { Text("WARNING: $it", color = MaterialTheme.colorScheme.error) }
        if (restarted) Text("検知プロセスを一時停止して再開しました。")
    }
}

@Composable
private fun SettingsScreen(state: UiState, vm: AppViewModel) {
    val draft = state.draftSettings
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { CompactHeader(state) }
        item {
            Column {
                Button(onClick = vm::saveSettings, enabled = draft != null && !state.loading, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Outlined.Save, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text(if (state.busyAction == "設定を保存中") "保存中..." else "設定を保存")
                }
                if (vm.hasUnsavedSettings()) {
                    Text(
                        "未保存の変更があります",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }
        }
        if (draft == null) {
            item { ConnectCard(state, vm) }
        } else {
            item { BasicSettings(draft, vm) }
            item { DetectionSettings(draft, vm) }
            item { SensorSettings(draft, vm) }
            item { SecondSleepAlarmSettings(draft, vm) }
            item { PhoneAlarmSettings(state, vm) }
            item { NotificationSettings(draft, vm, enabled = !state.loading) }
        }
    }
}

@Composable
private fun BasicSettings(settings: SettingsDto, vm: AppViewModel) = SectionCard("基本") {
    NumberField("体重 kg", settings.personWeightKg) { value -> vm.updateDraft { it.copy(personWeightKg = value) } }
    NumberField("読取間隔 秒", settings.sampleIntervalSec) { value -> vm.updateDraft { it.copy(sampleIntervalSec = value) } }
    TextFieldRow("ログ", settings.logPath) { value -> vm.updateDraft { it.copy(logPath = value) } }
    TextFieldRow("状態ファイル", settings.statusPath) { value -> vm.updateDraft { it.copy(statusPath = value) } }
}

@Composable
private fun DetectionSettings(settings: SettingsDto, vm: AppViewModel) = SectionCard("検知") {
    NumberField("離床しきい値", settings.exitRatio) { value -> vm.updateDraft { it.copy(exitRatio = value) } }
    NumberField("入床しきい値", settings.returnRatio) { value -> vm.updateDraft { it.copy(returnRatio = value) } }
    NumberField("監視時間 秒", settings.monitorSec) { value -> vm.updateDraft { it.copy(monitorSec = value) } }
    NumberField("確認時間 秒", settings.confirmSec) { value -> vm.updateDraft { it.copy(confirmSec = value) } }
    IntField("平滑化", settings.movingAverageWindow) { value -> vm.updateDraft { it.copy(movingAverageWindow = value) } }
}

@Composable
private fun SensorSettings(settings: SettingsDto, vm: AppViewModel) = SectionCard("センサー") {
    IntField("ウォームアップ", settings.warmupSamples) { value -> vm.updateDraft { it.copy(warmupSamples = value) } }
    IntField("中央値サンプル", settings.medianSamples) { value -> vm.updateDraft { it.copy(medianSamples = value) } }
    TextFieldRow("DATAピン", settings.dataPin) { value -> vm.updateDraft { it.copy(dataPin = value) } }
    TextFieldRow("CLOCKピン", settings.clockPin) { value -> vm.updateDraft { it.copy(clockPin = value) } }
    NumberField("HX711待機 秒", settings.hx711ReadyTimeoutSec) { value -> vm.updateDraft { it.copy(hx711ReadyTimeoutSec = value) } }
}

@Composable
private fun SecondSleepAlarmSettings(settings: SettingsDto, vm: AppViewModel) = SectionCard("二度寝検知アラーム") {
    ToggleRow("二度寝検知", "二度寝検知イベントを有効にする", settings.alarmEnabled) { value -> vm.updateDraft { it.copy(alarmEnabled = value) } }
    ToggleRow("ラズパイ側ブザー", "スマホ音を使う場合はOFF", settings.buzzerEnabled) { value -> vm.updateDraft { it.copy(buzzerEnabled = value) } }
    NumberField("鳴動時間 秒", settings.buzzerDurationSec) { value -> vm.updateDraft { it.copy(buzzerDurationSec = value) } }
    TextFieldRow("Webhook URL", settings.webhookUrl, password = true) { value -> vm.updateDraft { it.copy(webhookUrl = value) } }
    TextFieldRow("ブザーピン", settings.buzzerPin) { value -> vm.updateDraft { it.copy(buzzerPin = value) } }
    NumberField("パルス 秒", settings.buzzerPulseSec) { value -> vm.updateDraft { it.copy(buzzerPulseSec = value) } }
}

@Composable
private fun PhoneAlarmSettings(state: UiState, vm: AppViewModel) = SectionCard("スマホアラーム") {
    ToggleRow(
        "スマホで音を鳴らす",
        "時刻アラーム、再アラーム、二度寝検知で鳴らす",
        state.phoneAlarmEnabled,
        vm::setPhoneAlarmEnabled,
    )
    ToggleRow(
        "アラーム通知",
        "鳴動時に高優先度通知を出す",
        state.phoneAlarmNotificationsEnabled,
        vm::setPhoneAlarmNotificationsEnabled,
    )
    Text("音量 ${((state.phoneAlarmVolume * 100).toInt())}%", fontWeight = FontWeight.SemiBold)
    Slider(
        value = state.phoneAlarmVolume,
        onValueChange = vm::setPhoneAlarmVolume,
        valueRange = 0f..1f,
        steps = 9,
        enabled = state.phoneAlarmEnabled,
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(onClick = vm::testPhoneAlarm, modifier = Modifier.weight(1f)) {
            Text("テスト再生")
        }
        OutlinedButton(onClick = vm::dismissPhoneAlarm, modifier = Modifier.weight(1f)) {
            Text("停止")
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NotificationSettings(settings: SettingsDto, vm: AppViewModel, enabled: Boolean) = SectionCard("通知") {
    ToggleRow("Webhook", "Webhook通知を送る", settings.webhookEnabled) { value -> vm.updateDraft { it.copy(webhookEnabled = value) } }
    TextFieldRow("通知イベント", settings.webhookEvents.joinToString(",")) { value ->
        vm.updateDraft { it.copy(webhookEvents = value.split(",").map { item -> item.trim() }.filter { item -> item.isNotBlank() }) }
    }
    Text("形式", fontWeight = FontWeight.SemiBold)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("discord", "json").forEach { format ->
            FilterChip(
                selected = settings.webhookPayloadFormat == format,
                onClick = { vm.updateDraft { it.copy(webhookPayloadFormat = format) } },
                label = { Text(format) },
            )
        }
    }
    NumberField("タイムアウト 秒", settings.webhookTimeoutSec) { value -> vm.updateDraft { it.copy(webhookTimeoutSec = value) } }
    Spacer(Modifier.height(8.dp))
    OutlinedButton(onClick = vm::testWebhook, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
        Text("Webhookテスト")
    }
}

@Composable
private fun SectionCard(title: String? = null, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(16.dp)) {
            if (title != null) {
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(12.dp))
            }
            content()
        }
    }
}

@Composable
private fun ToggleRow(title: String, description: String? = null, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            if (description != null) {
                Text(description, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

@Composable
private fun SaveStatusLabel(status: String?) {
    if (status == null) return
    Text(
        when (status) {
            "保存中" -> "保存中..."
            else -> status
        },
        style = MaterialTheme.typography.bodySmall,
        color = if (status == "保存失敗") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun WeekdayToggleRow(weekdays: List<Int>, onToggle: (Int) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        WeekdayLabels.forEachIndexed { day, label ->
            val isSelected = weekdays.contains(day)
            FilterChip(
                selected = isSelected,
                onClick = { onToggle(day) },
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 48.dp)
                    .semantics { selected = isSelected },
                label = { Text(label) },
            )
        }
    }
}

@Composable
private fun TextFieldRow(label: String, value: String, password: Boolean = false, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        label = { Text(label) },
        visualTransformation = if (password) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        singleLine = true,
    )
}

@Composable
private fun NumberField(label: String, value: Double, onChange: (Double) -> Unit) {
    OutlinedTextField(
        value = value.cleanString(),
        onValueChange = { text -> text.toDoubleOrNull()?.let(onChange) },
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        label = { Text(label) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        singleLine = true,
    )
}

@Composable
private fun IntField(label: String, value: Int, onChange: (Int) -> Unit) {
    OutlinedTextField(
        value = value.toString(),
        onValueChange = { text -> text.toIntOrNull()?.let(onChange) },
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        label = { Text(label) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        singleLine = true,
    )
}

@Composable
private fun MetricGrid(items: List<Pair<String, String>>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.chunked(2).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                row.forEach { (label, value) ->
                    Column(Modifier.weight(1f)) {
                        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(value, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun ToneChip(text: String, tone: Tone) {
    AssistChip(onClick = {}, label = { Text(text) }, leadingIcon = { ToneDot(tone) })
}

@Composable
private fun ToneDot(tone: Tone) {
    val color = when (tone) {
        Tone.Sleep -> Color(0xFF007AFF)
        Tone.Watch -> Color(0xFFFF9F0A)
        Tone.Alert -> Color(0xFFFF3B30)
        Tone.Done -> Color(0xFF34C759)
        Tone.Idle -> Color(0xFF8E8E93)
    }
    Canvas(Modifier.width(10.dp).height(10.dp)) {
        drawCircle(color = color)
    }
}

@Composable
private fun Sparkline(values: List<Double>) {
    if (values.size < 2) return
    val lineColor = MaterialTheme.colorScheme.primary
    Canvas(Modifier.fillMaxWidth().height(56.dp).padding(top = 8.dp)) {
        val minValue = values.minOrNull() ?: 0.0
        val maxValue = values.maxOrNull() ?: 1.0
        val span = max(1e-6, maxValue - minValue)
        val step = size.width / max(1, values.lastIndex)
        val path = Path()
        values.forEachIndexed { index, value ->
            val x = index * step
            val y = size.height - (((value - minValue) / span).toFloat() * size.height)
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, color = lineColor, style = Stroke(width = 4f))
        val last = values.last()
        val lastY = size.height - (((last - minValue) / span).toFloat() * size.height)
        drawCircle(lineColor, radius = 6f, center = Offset(size.width, lastY))
    }
    Text(
        "在床値の推移（直近${values.size}点）  ${"%.1f".format(values.minOrNull() ?: 0.0)}〜${"%.1f".format(values.maxOrNull() ?: 0.0)} kg相当",
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun MissionProgress(rechecks: List<PendingRecheckDto>) {
    if (rechecks.isEmpty()) return
    val active = rechecks.maxBy { it.offBedElapsedSec }
    Spacer(Modifier.height(8.dp))
    Text(
        if (active.requiredOffBedSec > 0) {
            "起床ミッション ${active.offBedElapsedSec.toInt()} / ${active.requiredOffBedSec.toInt()} 秒"
        } else {
            "再アラーム中 ${active.realarmCount} 回"
        },
        fontWeight = FontWeight.SemiBold,
    )
}

private fun isRunning(status: StatusDto?): Boolean = status?.managedProcessRunning ?: status?.running ?: false

private fun presenceLabel(weightKg: Double?, settings: SettingsDto?): String {
    if (weightKg == null || settings == null) return "未判定"
    val exitThreshold = settings.personWeightKg * settings.exitRatio
    val returnThreshold = settings.personWeightKg * settings.returnRatio
    return when {
        weightKg < exitThreshold -> "離床"
        weightKg >= returnThreshold -> "在床"
        else -> "判定中"
    }
}

private fun formatAlarm(alarm: ScheduledAlarmDto?): String? {
    if (alarm == null) return null
    return "${alarm.time}${alarm.label.takeIf { it.isNotBlank() }?.let { " $it" } ?: ""}"
}

private fun formatRechecks(rechecks: List<PendingRecheckDto>): String {
    if (rechecks.isEmpty()) return "-"
    val active = rechecks.maxBy { it.offBedElapsedSec }
    val suffix = if (rechecks.size > 1) " (+${rechecks.size - 1})" else ""
    return if (active.offBedElapsedSec > 0 && active.requiredOffBedSec > 0) {
        "離床 ${active.offBedElapsedSec.toInt()}/${active.requiredOffBedSec.toInt()}秒$suffix"
    } else if (active.realarmCount > 0) {
        "再アラーム ${active.realarmCount}回$suffix"
    } else {
        "${rechecks.size}件 待機"
    }
}

private fun Double.cleanString(): String {
    val asLong = toLong()
    return if (this == asLong.toDouble()) asLong.toString() else toString()
}
