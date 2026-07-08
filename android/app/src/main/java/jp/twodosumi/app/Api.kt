package jp.twodosumi.app

import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

interface TwodosumiApi {
    @GET("api/settings")
    suspend fun getSettings(): SettingsResponse

    @POST("api/settings")
    suspend fun postSettings(@Body body: SettingsRequest): BasicResponse

    @POST("api/settings")
    suspend fun postPartialSettings(@Body body: PartialSettingsRequest): BasicResponse

    @GET("api/status")
    suspend fun getStatus(): StatusResponse

    @POST("api/run/start")
    suspend fun startRun(): BasicResponse

    @POST("api/run/stop")
    suspend fun stopRun(): BasicResponse

    @POST("api/calibration/zero")
    suspend fun calibrateZero(@Body body: SampleRequest): ZeroCalibrationResponse

    @POST("api/calibration/scale")
    suspend fun calibrateScale(@Body body: ScaleRequest): ScaleCalibrationResponse

    @POST("api/sensor/check")
    suspend fun checkSensor(@Body body: SensorCheckRequest): SensorCheckResponse

    @POST("api/test-webhook")
    suspend fun testWebhook(): BasicResponse
}

class ApiFactory {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    fun create(baseUrl: String, token: String): TwodosumiApi {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        val client = OkHttpClient.Builder()
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val request = chain.request().newBuilder()
                    .header("Content-Type", "application/json")
                    .header("X-2Dosumi-Token", token)
                    .build()
                chain.proceed(request)
            }
            .addInterceptor(logging)
            .build()

        return Retrofit.Builder()
            .baseUrl(normalizeBaseUrl(baseUrl))
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(TwodosumiApi::class.java)
    }

    private fun normalizeBaseUrl(value: String): String {
        val trimmed = value.trim()
        val withScheme = if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
            trimmed
        } else {
            "http://$trimmed"
        }
        return if (withScheme.endsWith("/")) withScheme else "$withScheme/"
    }
}
