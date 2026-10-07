package com.callpilot.app

import android.content.Context
import android.net.ConnectivityManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.net.URL

fun parseDiscoveryReply(msg: String, senderIp: String): String? {
    val trimmed = msg.trim()
    val parts = trimmed.split(Regex("\\s+"))
    if (parts.size != 2 || parts[0] != "CALLPILOT") return null
    val port = parts[1].toIntOrNull() ?: return null
    if (port !in 1..65535) return null
    return "http://$senderIp:$port"
}

private fun ping(baseUrl: String, timeoutMs: Int = 1500): Boolean {
    var conn: HttpURLConnection? = null
    return try {
        val fullUrl = if (baseUrl.endsWith("/")) "${baseUrl}api/status" else "$baseUrl/api/status"
        val url = URL(fullUrl)
        conn = url.openConnection() as HttpURLConnection
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        conn.requestMethod = "GET"
        conn.responseCode in 200..299
    } catch (_: Exception) {
        false
    } finally {
        conn?.disconnect()
    }
}

suspend fun findServer(ctx: Context, lastKnown: String?): String? = withContext(Dispatchers.IO) {
    // 1. Check lastKnown if provided
    if (!lastKnown.isNullOrBlank() && ping(lastKnown, 1500)) {
        return@withContext lastKnown
    }

    // 2. Windows Mobile Hotspot default host address
    val hotspotHost = "http://192.168.137.1:8001"
    if (ping(hotspotHost, 1500)) {
        return@withContext hotspotHost
    }

    // 3. UDP broadcast to 255.255.255.255 and directed broadcast of active network
    val targets = mutableListOf<InetAddress>()
    val localV4 = mutableListOf<ByteArray>()
    try {
        targets.add(InetAddress.getByName("255.255.255.255"))
    } catch (_: Exception) {}

    try {
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
        val active = cm?.activeNetwork
        val lp = active?.let { cm.getLinkProperties(it) }
        lp?.linkAddresses?.forEach { linkAddr ->
            val addr = linkAddr.address
            val prefix = linkAddr.prefixLength
            if (addr is Inet4Address && prefix in 1..31) {
                val raw = addr.address
                localV4.add(raw)
                val mask = (-1L shl (32 - prefix)).toInt()
                val bcast = ByteArray(4)
                for (i in 0..3) {
                    val ipByte = raw[i].toInt() and 0xFF
                    val maskByte = (mask shr ((3 - i) * 8)) and 0xFF
                    bcast[i] = (ipByte or (maskByte.inv() and 0xFF)).toByte()
                }
                val directBcast = InetAddress.getByAddress(bcast)
                if (!targets.contains(directBcast)) {
                    targets.add(directBcast)
                }
            }
        }
    } catch (_: Exception) {}

    try {
        DatagramSocket().apply {
            broadcast = true
            soTimeout = 2500
        }.use { socket ->
            val payload = "CALLPILOT_DISCOVER".toByteArray(Charsets.UTF_8)
            for (target in targets) {
                try {
                    val packet = DatagramPacket(payload, payload.size, target, 8002)
                    socket.send(packet)
                } catch (_: Exception) {}
            }

            val buf = ByteArray(1024)
            val recvPacket = DatagramPacket(buf, buf.size)
            val deadline = System.currentTimeMillis() + 2500
            while (System.currentTimeMillis() < deadline) {
                val remaining = (deadline - System.currentTimeMillis()).toInt()
                if (remaining <= 0) break
                socket.soTimeout = remaining
                try {
                    socket.receive(recvPacket)
                    val text = String(recvPacket.data, recvPacket.offset, recvPacket.length, Charsets.UTF_8)
                    val senderIp = recvPacket.address.hostAddress ?: continue
                    val resolved = parseDiscoveryReply(text, senderIp)
                    if (resolved != null) {
                        return@withContext resolved
                    }
                } catch (_: SocketTimeoutException) {
                    break
                }
            }
        }
    } catch (_: Exception) {}

    // 4. Many routers drop Wi-Fi broadcasts: probe every host of our /24 directly
    // ponytail: only the /24 around our IP, wider subnets would need a smarter scan
    val hosts = localV4.flatMap { raw ->
        val p = "${raw[0].toInt() and 0xFF}.${raw[1].toInt() and 0xFF}.${raw[2].toInt() and 0xFF}"
        (1..254).map { "http://$p.$it:8001" }
    }.distinct()
    coroutineScope {
        hosts.map { url -> async { url.takeIf { ping(it, 500) } } }.awaitAll().firstOrNull { it != null }
    }
}
