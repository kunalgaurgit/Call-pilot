package com.callpilot.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

private const val LATEST = "https://github.com/kunalgaurgit/Call-pilot/releases/latest/download"

data class AppUpdate(val versionName: String, val apkUrl: String, val sha256: String)

private fun open(url: String): HttpURLConnection =
    (URL(url).openConnection() as HttpURLConnection).apply {
        connectTimeout = 10_000
        readTimeout = 20_000
    }

/** Newer release from GitHub, null when up to date; throws on network errors. */
suspend fun checkForUpdate(): AppUpdate? = withContext(Dispatchers.IO) {
    val conn = open("$LATEST/update.json")
    try {
        val json = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
        val name = json.getString("versionName")
        if (json.getInt("versionCode") <= BuildConfig.VERSION_CODE) null
        else AppUpdate(name, "$LATEST/CallPilot-$name.apk", json.getString("sha256"))
    } finally {
        conn.disconnect()
    }
}

/** Downloads the APK into cache and checks it against the release's sha256; throws on failure. */
suspend fun downloadUpdate(ctx: Context, update: AppUpdate, onProgress: (Int) -> Unit): File =
    withContext(Dispatchers.IO) {
        val file = File(ctx.cacheDir, "updates/CallPilot.apk").apply { parentFile?.mkdirs() }
        val digest = MessageDigest.getInstance("SHA-256")
        val conn = open(update.apkUrl)
        try {
            val total = conn.contentLengthLong
            var done = 0L
            conn.inputStream.use { input ->
                file.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        digest.update(buf, 0, n)
                        done += n
                        if (total > 0) onProgress((done * 100 / total).toInt())
                    }
                }
            }
        } finally {
            conn.disconnect()
        }
        val hash = digest.digest().joinToString("") { "%02x".format(it) }
        if (!hash.equals(update.sha256, ignoreCase = true)) {
            file.delete()
            error("Download corrupted, please try again")
        }
        file
    }

/** Opens the system installer; false when the user must first allow installs from this app. */
fun installUpdate(ctx: Context, apk: File): Boolean {
    if (!ctx.packageManager.canRequestPackageInstalls()) {
        ctx.startActivity(
            Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
        return false
    }
    val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", apk)
    ctx.startActivity(
        Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
    )
    return true
}
