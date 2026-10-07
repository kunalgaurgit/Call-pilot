package com.callpilot.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private const val LATEST = "https://github.com/kunalgaurgit/Call-pilot/releases/latest/download"

/** (versionName, APK download URL) of a newer release, null when up to date; throws on network errors. */
suspend fun checkForUpdate(): Pair<String, String>? = withContext(Dispatchers.IO) {
    val conn = URL("$LATEST/update.json").openConnection() as HttpURLConnection
    conn.connectTimeout = 8000
    conn.readTimeout = 8000
    try {
        val json = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
        val name = json.getString("versionName")
        if (json.getInt("versionCode") > BuildConfig.VERSION_CODE) name to "$LATEST/CallPilot-$name.apk" else null
    } finally {
        conn.disconnect()
    }
}
