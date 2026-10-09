package com.callpilot.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

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
    val advice: List<String> = emptyList()
)

data class Turn(
    val reply: String,
    val state: String,
    val bookingId: String? = null,
    val pdfUrl: String? = null,
    val rx: Rx? = null
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
    val pdfUrl: String
)

class Api(var baseUrl: String) {

    private fun cleanBaseUrl(): String = baseUrl.trim().trimEnd('/')

    private fun openConnection(endpoint: String, method: String): HttpURLConnection {
        val base = cleanBaseUrl()
        val path = if (endpoint.startsWith("/")) endpoint else "/$endpoint"
        val url = URL("$base$path")
        val conn = url.openConnection() as HttpURLConnection
        conn.connectTimeout = 3000
        conn.readTimeout = 25000
        conn.requestMethod = method
        return conn
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

    private fun parseRx(obj: JSONObject): Rx? {
        val rxObj = obj.optJSONObject("rx") ?: return null
        val condition = rxObj.optString("condition", "")
        val medicines = mutableListOf<Medicine>()
        val medsArr = rxObj.optJSONArray("medicines")
        if (medsArr != null) {
            for (i in 0 until medsArr.length()) {
                val medObj = medsArr.optJSONObject(i) ?: continue
                val name = medObj.optString("name", "")
                val strength = if (!medObj.isNull("strength")) medObj.optString("strength", "") else ""
                val dose = if (!medObj.isNull("dose")) medObj.optString("dose", "") else ""
                val frequency = if (!medObj.isNull("frequency")) medObj.optString("frequency", "") else ""
                val days = if (!medObj.isNull("days")) {
                    val d = medObj.opt("days")
                    if (d == null || d == JSONObject.NULL) "" else d.toString()
                } else ""
                medicines.add(Medicine(name = name, strength = strength, dose = dose, frequency = frequency, days = days))
            }
        }
        val advice = mutableListOf<String>()
        val adviceArr = rxObj.optJSONArray("advice")
        if (adviceArr != null) {
            for (i in 0 until adviceArr.length()) {
                val item = adviceArr.optString(i, "")
                if (item.isNotEmpty() && item != "null") {
                    advice.add(item)
                }
            }
        }
        return Rx(
            condition = condition,
            medicines = medicines,
            advice = advice
        )
    }

    suspend fun turn(sid: String, text: String): Turn = withContext(Dispatchers.IO) {
        val conn = openConnection("/api/call/$sid/turn", "POST")
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
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
        Turn(
            reply = reply,
            state = state,
            bookingId = bookingId,
            pdfUrl = pdfUrl,
            rx = rx
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
            pdfUrl = pdfUrl
        )
    }
}
