package jp.twodosumi.app

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Serializable
data class SettingsResponse(
    val ok: Boolean = false,
    val error: String? = null,
    val settings: SettingsDto? = null,
)

@Serializable
data class StatusResponse(
    val ok: Boolean = false,
    val error: String? = null,
    val status: StatusDto? = null,
)

@Serializable
data class BasicResponse(
    val ok: Boolean = false,
    val error: String? = null,
    val running: Boolean? = null,
)

@Serializable
data class ZeroCalibrationResponse(
    val ok: Boolean = false,
    val error: String? = null,
    @SerialName("zero_offset") val zeroOffset: Double? = null,
    val restarted: Boolean = false,
)

@Serializable
data class ScaleCalibrationResponse(
    val ok: Boolean = false,
    val error: String? = null,
    @SerialName("scale_factor") val scaleFactor: Double? = null,
    val restarted: Boolean = false,
)

@Serializable
data class SensorCheckResponse(
    val ok: Boolean = false,
    val error: String? = null,
    val sensor: SensorCheckResultDto? = null,
    val restarted: Boolean = false,
)

@Serializable
data class SettingsRequest(val settings: SettingsDto)

@Serializable
data class PartialSettingsRequest(val settings: Map<String, JsonElement>)

@Serializable
data class SampleRequest(val samples: Int)

@Serializable
data class ScaleRequest(
    val samples: Int,
    @SerialName("known_kg") val knownKg: Double,
)

@Serializable
data class SensorCheckRequest(
    val samples: Int,
    @SerialName("interval_sec") val intervalSec: Double = 0.1,
)

@Serializable
data class SettingsDto(
    val reader: String = "",
    @SerialName("log_path") val logPath: String = "",
    @SerialName("status_path") val statusPath: String = "",
    @SerialName("load_cell_layout") val loadCellLayout: String = "",
    @SerialName("zero_offset") val zeroOffset: Double = 0.0,
    @SerialName("scale_factor") val scaleFactor: Double = 1.0,
    @SerialName("person_weight_kg") val personWeightKg: Double = 60.0,
    @SerialName("sample_interval_sec") val sampleIntervalSec: Double = 1.0,
    @SerialName("warmup_samples") val warmupSamples: Int = 5,
    @SerialName("median_samples") val medianSamples: Int = 9,
    @SerialName("moving_average_window") val movingAverageWindow: Int = 5,
    @SerialName("exit_ratio") val exitRatio: Double = 0.3,
    @SerialName("return_ratio") val returnRatio: Double = 0.4,
    @SerialName("monitor_sec") val monitorSec: Double = 1800.0,
    @SerialName("confirm_sec") val confirmSec: Double = 180.0,
    @SerialName("data_pin") val dataPin: String = "D6",
    @SerialName("clock_pin") val clockPin: String = "D5",
    @SerialName("hx711_ready_timeout_sec") val hx711ReadyTimeoutSec: Double = 3.0,
    @SerialName("alarm_enabled") val alarmEnabled: Boolean = false,
    @SerialName("buzzer_enabled") val buzzerEnabled: Boolean = true,
    @SerialName("buzzer_pin") val buzzerPin: String = "D13",
    @SerialName("buzzer_duration_sec") val buzzerDurationSec: Double = 5.0,
    @SerialName("buzzer_pulse_sec") val buzzerPulseSec: Double = 0.25,
    @SerialName("scheduled_alarm_enabled") val scheduledAlarmEnabled: Boolean = true,
    @SerialName("scheduled_alarms") val scheduledAlarms: List<ScheduledAlarmDto> = emptyList(),
    @SerialName("bed_recheck_minutes") val bedRecheckMinutes: Double = 5.0,
    @SerialName("wake_mission_enabled") val wakeMissionEnabled: Boolean = true,
    @SerialName("wake_mission_required_off_bed_sec") val wakeMissionRequiredOffBedSec: Double = 30.0,
    @SerialName("webhook_enabled") val webhookEnabled: Boolean = false,
    @SerialName("webhook_events") val webhookEvents: List<String> = listOf("second_sleep_detected"),
    @SerialName("webhook_payload_format") val webhookPayloadFormat: String = "discord",
    @SerialName("webhook_timeout_sec") val webhookTimeoutSec: Double = 5.0,
    @SerialName("webhook_url") val webhookUrl: String = "",
    @SerialName("web_ui_token_configured") val webUiTokenConfigured: Boolean = false,
    @SerialName("known_events") val knownEvents: List<String> = emptyList(),
)

@Serializable
data class ScheduledAlarmDto(
    val id: String,
    val time: String = "07:00",
    val enabled: Boolean = true,
    val label: String = "",
    val weekdays: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6),
)

@Serializable
data class StatusDto(
    val timestamp: String? = null,
    val pid: Int? = null,
    val running: Boolean = false,
    val raw: Double? = null,
    @SerialName("weight_kg") val weightKg: Double? = null,
    @SerialName("smoothed_weight_kg") val smoothedWeightKg: Double? = null,
    val state: String = "",
    val event: String = "",
    val message: String = "",
    @SerialName("managed_process_running") val managedProcessRunning: Boolean? = null,
    @SerialName("next_scheduled_alarm") val nextScheduledAlarm: ScheduledAlarmDto? = null,
    @SerialName("pending_rechecks") val pendingRechecks: List<PendingRecheckDto>? = emptyList(),
)

@Serializable
data class PendingRecheckDto(
    val id: String = "",
    val time: String = "",
    val label: String = "",
    @SerialName("due_at") val dueAt: String? = null,
    @SerialName("off_bed_since") val offBedSince: String? = null,
    @SerialName("off_bed_elapsed_sec") val offBedElapsedSec: Double = 0.0,
    @SerialName("required_off_bed_sec") val requiredOffBedSec: Double = 0.0,
    @SerialName("realarm_count") val realarmCount: Int = 0,
)

@Serializable
data class SensorCheckResultDto(
    val ok: Boolean = false,
    val reader: String = "",
    @SerialName("samples_requested") val samplesRequested: Int = 0,
    @SerialName("samples_read") val samplesRead: Int = 0,
    @SerialName("raw_min") val rawMin: Double? = null,
    @SerialName("raw_max") val rawMax: Double? = null,
    @SerialName("raw_median") val rawMedian: Double? = null,
    @SerialName("raw_span") val rawSpan: Double? = null,
    @SerialName("weight_median_kg") val weightMedianKg: Double? = null,
    @SerialName("duration_sec") val durationSec: Double = 0.0,
    val message: String = "",
    val warnings: List<String> = emptyList(),
)

data class EventEntry(
    val label: String,
    val detail: String,
    val tone: Tone,
    val time: String,
)

enum class Tone { Idle, Sleep, Watch, Alert, Done }

data class StateMeta(val label: String, val tone: Tone)

val StateLabels = mapOf(
    "SLEEPING" to StateMeta("在床", Tone.Sleep),
    "AWAKE_WINDOW" to StateMeta("離床・監視中", Tone.Watch),
    "RETURNED" to StateMeta("再入床", Tone.Watch),
    "SECOND_SLEEP" to StateMeta("二度寝検知", Tone.Alert),
    "DONE" to StateMeta("起床完了", Tone.Done),
)

val WeekdayLabels = listOf("月", "火", "水", "木", "金", "土", "日")

fun formatWeekdaySummary(weekdays: List<Int>): String {
    val normalized = weekdays.distinct().sorted()
    return when (normalized) {
        emptyList<Int>() -> "曜日未設定"
        (0..6).toList() -> "毎日"
        (0..4).toList() -> "平日"
        listOf(5, 6) -> "週末"
        else -> normalized.mapNotNull { WeekdayLabels.getOrNull(it) }.joinToString("・")
    }
}

fun formatLocalTime(timestamp: String?, pattern: String): String {
    if (timestamp.isNullOrBlank()) return "--:--"
    val formatter = DateTimeFormatter.ofPattern(pattern)
    return runCatching {
        OffsetDateTime.parse(timestamp)
            .atZoneSameInstant(ZoneId.systemDefault())
            .format(formatter)
    }.recoverCatching {
        LocalDateTime.parse(timestamp).format(formatter)
    }.getOrElse {
        timestamp.substringAfter("T", timestamp).substringAfter(" ", timestamp).take(pattern.length)
    }
}
