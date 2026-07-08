package jp.twodosumi.app

import java.util.TimeZone
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

class FormattingTest {
    private lateinit var originalTimeZone: TimeZone

    @Before
    fun setUp() {
        originalTimeZone = TimeZone.getDefault()
        TimeZone.setDefault(TimeZone.getTimeZone("Asia/Tokyo"))
    }

    @After
    fun tearDown() {
        TimeZone.setDefault(originalTimeZone)
    }

    @Test
    fun weekdaySummaryUsesCommonGroupsAndFallback() {
        assertEquals("曜日未設定", formatWeekdaySummary(emptyList()))
        assertEquals("毎日", formatWeekdaySummary((0..6).toList()))
        assertEquals("平日", formatWeekdaySummary((0..4).toList()))
        assertEquals("週末", formatWeekdaySummary(listOf(5, 6)))
        assertEquals("月・水・金", formatWeekdaySummary(listOf(4, 0, 2)))
    }

    @Test
    fun offsetTimestampIsRenderedInLocalTime() {
        assertEquals("09:30", formatLocalTime("2026-07-02T00:30:00+00:00", "HH:mm"))
        assertEquals("09:30:00", formatLocalTime("2026-07-02T00:30:00Z", "HH:mm:ss"))
    }

    @Test
    fun localTimestampAndMissingTimestampHaveFallbacks() {
        assertEquals("07:05", formatLocalTime("2026-07-02T07:05:00", "HH:mm"))
        assertEquals("--:--", formatLocalTime(null, "HH:mm"))
    }
}
