package com.callpilot.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class ServerUnreachable(cause: IOException) : IOException("Cannot reach the server", cause)

data class Start(
    val sessionId: String,
    val greeting: String,
    val business: String
)

data class Medicine(
    val name: String,
    val strength: String = "",
    val dose: String = "",
    val frequency: String = "",
    val days: String = ""
)

data class Rx(
    val condition: String,
    val medicines: List<Medicine> = emptyList(),
    val advice: List<String> = emptyList(),
    val ayurvedic: List<Medicine> = emptyList(),
    val homeopathic: List<Medicine> = emptyList(),
    val homeRemedies: List<String> = emptyList(),
    val seeDoctorIf: List<String> = emptyList()
)

data class Turn(
    val reply: String,
    val state: String,
    val bookingId: String? = null,
    val pdfUrl: String? = null,
    val rx: Rx? = null,
    val fields: Map<String, String> = emptyMap()
)

data class Booking(
    val id: Int,
    val sessionId: String,
    val doctor: String,
    val department: String,
    val appointmentDate: String,
    val appointmentTime: String,
    val hospitalBranch: String,
    val patientName: String,
    val phone: String,
    val age: String,
    val gender: String,
    val cityArea: String,
    val symptoms: String,
    val createdAt: String,
    val bookingId: String,
    val pdfUrl: String,
    val rx: Rx? = null
)

class Api(var baseUrl: String) {

    private fun cleanBaseUrl(): String = baseUrl.trim().trimEnd('/')

    private fun openConnection(endpoint: String, method: String): HttpURLConnection {
        val base = cleanBaseUrl()
        val path = if (endpoint.startsWith("/")) endpoint else "/$endpoint"
        val url = URL("$base$path")
        val conn = url.openConnection() as HttpURLConnection
        // 8 s: a phone waking its Wi-Fi from power-save can take several seconds to connect
        conn.connectTimeout = 8000
        conn.readTimeout = 25000
        conn.requestMethod = method
        return conn
    }

    // Only the connect step is retried: nothing has been sent yet, so the server never runs a turn twice.
    private fun openPostWithRetry(endpoint: String): HttpURLConnection {
        var last: IOException? = null
        for (attempt in 1..3) {
            val conn = openConnection(endpoint, "POST")
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            try {
                conn.connect()
                return conn
            } catch (e: IOException) {
                conn.disconnect()
                last = e
                if (attempt < 3) Thread.sleep(1000L * attempt)
            }
        }
        throw ServerUnreachable(last!!)
    }

    suspend fun startCall(): Start = withContext(Dispatchers.IO) {
        val conn = openConnection("/api/call/start", "POST")
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        val body = JSONObject().apply {
            put("config_id", "ai_doctor")
            put("use_fake", false)
        }
        conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }

        val code = conn.responseCode
        if (code !in 200..299) {
            val err = conn.errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP $code"
            conn.disconnect()
            throw IOException("startCall failed: HTTP $code - $err")
        }

        val responseText = conn.inputStream.bufferedReader().use { it.readText() }
        conn.disconnect()
        val obj = JSONObject(responseText)
        Start(
            sessionId = obj.getString("session_id"),
            greeting = obj.optString("greeting", ""),
            business = obj.optString("business", "")
        )
    }

    private fun str(o: JSONObject, key: String): String =
        if (o.isNull(key)) "" else o.optString(key, "")

    private fun medicines(arr: JSONArray?): List<Medicine> =
        (0 until (arr?.length() ?: 0)).mapNotNull { arr!!.optJSONObject(it) }.map {
            Medicine(str(it, "name"), str(it, "strength"), str(it, "dose"), str(it, "frequency"), str(it, "days"))
        }

    private fun strings(arr: JSONArray?): List<String> =
        (0 until (arr?.length() ?: 0)).map { arr!!.optString(it, "") }.filter { it.isNotEmpty() && it != "null" }

    fun parseRx(obj: JSONObject): Rx? {
        val rxObj = obj.optJSONObject("rx") ?: return null
        return Rx(
            condition = rxObj.optString("condition", ""),
            medicines = medicines(rxObj.optJSONArray("medicines")),
            advice = strings(rxObj.optJSONArray("advice")),
            ayurvedic = medicines(rxObj.optJSONArray("ayurvedic")),
            homeopathic = medicines(rxObj.optJSONArray("homeopathic")),
            homeRemedies = strings(rxObj.optJSONArray("home_remedies")),
            seeDoctorIf = strings(rxObj.optJSONArray("see_doctor_if"))
        )
    }

    suspend fun turn(sid: String, text: String): Turn = withContext(Dispatchers.IO) {
        val conn = openPostWithRetry("/api/call/$sid/turn")
        val body = JSONObject().apply {
            put("text", text)
        }
        conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }

        val code = conn.responseCode
        if (code !in 200..299) {
            val err = conn.errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP $code"
            conn.disconnect()
            throw IOException("turn failed: HTTP $code - $err")
        }

        val responseText = conn.inputStream.bufferedReader().use { it.readText() }
        conn.disconnect()
        val obj = JSONObject(responseText)
        val reply = obj.optString("reply", "")
        val state = obj.optString("state", "")
        val bookingId = if (obj.has("booking_id") && !obj.isNull("booking_id")) obj.getString("booking_id") else null
        val pdfUrl = if (obj.has("pdf_url") && !obj.isNull("pdf_url")) obj.getString("pdf_url") else null
        val rx = parseRx(obj)
        val fieldsObj = obj.optJSONObject("fields")
        val fields = fieldsObj?.keys()?.asSequence()?.associateWith { str(fieldsObj, it) } ?: emptyMap()
        Turn(
            reply = reply,
            state = state,
            bookingId = bookingId,
            pdfUrl = pdfUrl,
            rx = rx,
            fields = fields
        )
    }

    suspend fun hangup(sid: String) = withContext(Dispatchers.IO) {
        try {
            val conn = openConnection("/api/call/$sid/hangup", "POST")
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.outputStream.use { it.write("{}".toByteArray(Charsets.UTF_8)) }
            conn.responseCode
            conn.disconnect()
        } catch (_: Exception) {
            // Ignore hangup errors per brief
        }
    }

    suspend fun booking(sid: String): Booking? = withContext(Dispatchers.IO) {
        val conn = openConnection("/api/bookings/$sid", "GET")
        val code = conn.responseCode
        if (code == 404) {
            conn.disconnect()
            return@withContext null
        }
        if (code !in 200..299) {
            val err = conn.errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP $code"
            conn.disconnect()
            throw IOException("booking failed: HTTP $code - $err")
        }

        val responseText = conn.inputStream.bufferedReader().use { it.readText() }
        conn.disconnect()
        val obj = JSONObject(responseText)
        val id = obj.optInt("id", 0)
        val bookingId = when {
            obj.has("booking_id") && !obj.isNull("booking_id") -> obj.getString("booking_id")
            id > 0 -> "HB-%04d".format(id)
            else -> ""
        }
        val pdfUrl = obj.optString("pdf_url", "/api/bookings/$sid/pdf")
        Booking(
            id = id,
            sessionId = obj.optString("session_id", sid),
            doctor = obj.optString("doctor", ""),
            department = obj.optString("department", ""),
            appointmentDate = obj.optString("appointment_date", ""),
            appointmentTime = obj.optString("appointment_time", ""),
            hospitalBranch = obj.optString("hospital_branch", ""),
            patientName = obj.optString("patient_name", ""),
            phone = obj.optString("phone", ""),
            age = obj.optString("age", ""),
            gender = obj.optString("gender", ""),
            cityArea = obj.optString("city_area", ""),
            symptoms = obj.optString("symptoms", ""),
            createdAt = obj.optString("created_at", ""),
            bookingId = bookingId,
            pdfUrl = pdfUrl,
            rx = parseRx(obj)
        )
    }

    /** /api/status for the dialer's info panel; null when the server is unreachable. */
    suspend fun status(): JSONObject? = withContext(Dispatchers.IO) {
        try {
            val conn = openConnection("/api/status", "GET")
            conn.connectTimeout = 2000
            conn.readTimeout = 3000
            val text = if (conn.responseCode in 200..299) conn.inputStream.bufferedReader().use { it.readText() } else null
            conn.disconnect()
            text?.let { JSONObject(it) }
        } catch (_: Exception) {
            null
        }
    }
}
