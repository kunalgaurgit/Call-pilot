package com.callpilot.app

import android.app.Application
import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL

enum class Screen {
    DIALER,
    IN_CALL,
    ENDED,
    APPOINTMENTS,
    SETTINGS
}

data class Ended(
    val bookingId: String? = null,
    val doctor: String? = null,
    val department: String? = null,
    val date: String? = null,
    val time: String? = null,
    val branch: String? = null,
    val pdfUrl: String? = null,
    val message: String = "",
    val emergency: Boolean = false
)

class CallViewModel(application: Application) : AndroidViewModel(application) {

    private val prefs = application.getSharedPreferences("callpilot", Context.MODE_PRIVATE)
    private val voice = Voice(application)
    private val api = Api("")

    var screen by mutableStateOf(Screen.DIALER)
    var callStatus by mutableStateOf("Connecting")
    var agentLine by mutableStateOf("")
    var callerLine by mutableStateOf("")
    var seconds by mutableIntStateOf(0)
    var muted by mutableStateOf(false)
    var speaker by mutableStateOf(false)
    var serverUrl by mutableStateOf("")
    var serverState by mutableStateOf("Searching")
    var ended by mutableStateOf(Ended())
    var appointments by mutableStateOf<List<Booking>>(emptyList())

    private var timerJob: Job? = null
    private var missCount = 0
    private var currentSessionId: String? = null

    init {
        val lastKnown = prefs.getString("server", null)
        if (!lastKnown.isNullOrBlank()) {
            serverUrl = lastKnown
            api.baseUrl = lastKnown
        }
        retrySearch()
    }

    fun retrySearch() {
        viewModelScope.launch {
            serverState = "Searching"
            val lastKnown = prefs.getString("server", null)
            val found = findServer(getApplication(), lastKnown)
            if (found != null) {
                serverUrl = found
                api.baseUrl = found
                serverState = "Connected"
                prefs.edit().putString("server", found).apply()
            } else {
                serverState = "Not found"
            }
        }
    }

    fun saveServerUrl(url: String) {
        val cleaned = url.trim()
        serverUrl = cleaned
        api.baseUrl = cleaned
        prefs.edit().putString("server", cleaned).apply()
        viewModelScope.launch {
            serverState = "Searching"
            val ok = withContext(Dispatchers.IO) {
                var conn: HttpURLConnection? = null
                try {
                    val fullUrl = if (cleaned.endsWith("/")) "${cleaned}api/status" else "$cleaned/api/status"
                    val u = URL(fullUrl)
                    conn = u.openConnection() as HttpURLConnection
                    conn.connectTimeout = 1500
                    conn.readTimeout = 1500
                    conn.responseCode in 200..299
                } catch (_: Exception) {
                    false
                } finally {
                    conn?.disconnect()
                }
            }
            serverState = if (ok) "Connected" else "Not found"
        }
    }

    private fun startTimer() {
        seconds = 0
        timerJob?.cancel()
        timerJob = viewModelScope.launch {
            while (isActive && screen == Screen.IN_CALL) {
                delay(1000)
                seconds++
            }
        }
    }

    fun call() {
        if (screen == Screen.IN_CALL) return
        viewModelScope.launch {
            if (serverState != "Connected" || serverUrl.isBlank()) {
                serverState = "Searching"
                val lastKnown = prefs.getString("server", null)
                val found = findServer(getApplication(), lastKnown)
                if (found != null) {
                    serverUrl = found
                    api.baseUrl = found
                    serverState = "Connected"
                    prefs.edit().putString("server", found).apply()
                } else {
                    serverState = "Not found"
                    return@launch
                }
            }

            screen = Screen.IN_CALL
            callStatus = "Ringing"
            agentLine = ""
            callerLine = ""
            muted = false
            speaker = false
            missCount = 0
            currentSessionId = null
            voice.setSpeaker(false)
            startTimer()

            // ToneGenerator for ringback tone
            withContext(Dispatchers.IO) {
                var tone: ToneGenerator? = null
                try {
                    tone = ToneGenerator(AudioManager.STREAM_VOICE_CALL, 80)
                    tone.startTone(ToneGenerator.TONE_SUP_RINGTONE, 2500)
                    delay(2500)
                } catch (_: Exception) {
                    delay(2500)
                } finally {
                    try {
                        tone?.stopTone()
                        tone?.release()
                    } catch (_: Exception) {}
                }
            }

            if (screen != Screen.IN_CALL) return@launch

            callStatus = "Connecting"
            try {
                val start = api.startCall()
                currentSessionId = start.sessionId
                agentLine = start.greeting
                speakAgent(start.greeting)
            } catch (e: Exception) {
                endCallInternal("Connection failed: ${e.message ?: "Server error"}")
            }
        }
    }

    private fun speakAgent(text: String, onDone: (() -> Unit)? = null) {
        if (screen != Screen.IN_CALL) return
        callStatus = "Speaking"
        voice.speak(text) {
            if (screen != Screen.IN_CALL) return@speak
            if (onDone != null) {
                onDone()
            } else {
                // HALF-DUPLEX: wait 300 ms before listening
                viewModelScope.launch {
                    delay(300)
                    if (screen == Screen.IN_CALL && !muted) {
                        startListening()
                    }
                }
            }
        }
    }

    private fun startListening() {
        if (screen != Screen.IN_CALL || muted) return
        callStatus = "Listening"
        voice.listen(
            onText = { text ->
                missCount = 0
                onCallerText(text)
            },
            onMiss = {
                onSpeechMiss()
            },
            onFatal = { msg ->
                endCallInternal(msg)
            }
        )
    }

    private fun onCallerText(text: String) {
        if (screen != Screen.IN_CALL) return
        callerLine = text
        callStatus = "Thinking"
        val sid = currentSessionId ?: return
        viewModelScope.launch {
            try {
                val turn = api.turn(sid, text)
                agentLine = turn.reply
                val isDone = turn.state == "done"
                val isEscalated = turn.state == "escalated"
                if (isDone || isEscalated) {
                    val bookingId = turn.bookingId
                    val pdfUrl = turn.pdfUrl
                    val isEmergency = turn.reply.contains("108")
                    speakAgent(turn.reply) {
                        viewModelScope.launch {
                            finishCall(
                                sid = sid,
                                bookingId = bookingId,
                                pdfUrl = pdfUrl,
                                message = turn.reply,
                                emergency = isEmergency
                            )
                        }
                    }
                } else {
                    speakAgent(turn.reply)
                }
            } catch (_: Exception) {
                speakAgent("Sorry, the line is not clear. Please say that again.")
            }
        }
    }

    private fun onSpeechMiss() {
        if (screen != Screen.IN_CALL || muted) return
        missCount++
        when (missCount) {
            1 -> {
                startListening()
            }
            2 -> {
                speakAgent("Sorry, I can't hear you. Please speak now.")
            }
            else -> {
                val sid = currentSessionId
                viewModelScope.launch {
                    if (sid != null) {
                        api.hangup(sid)
                    }
                    endCallInternal("Call ended - no response")
                }
            }
        }
    }

    private suspend fun finishCall(
        sid: String,
        bookingId: String?,
        pdfUrl: String?,
        message: String,
        emergency: Boolean
    ) {
        timerJob?.cancel()
        voice.endAudio()
        var appt: Booking? = null
        if (bookingId != null) {
            saveBookingSession(sid)
            appt = try { api.booking(sid) } catch (_: Exception) { null }
        }
        ended = Ended(
            bookingId = appt?.bookingId ?: bookingId,
            doctor = appt?.doctor,
            department = appt?.department,
            date = appt?.appointmentDate,
            time = appt?.appointmentTime,
            branch = appt?.hospitalBranch,
            pdfUrl = appt?.pdfUrl ?: pdfUrl,
            message = message,
            emergency = emergency
        )
        screen = Screen.ENDED
    }

    private fun endCallInternal(msg: String) {
        timerJob?.cancel()
        voice.stopSpeaking()
        voice.stopListening()
        voice.endAudio()
        ended = Ended(message = msg)
        screen = Screen.ENDED
    }

    fun endCall() {
        val sid = currentSessionId
        viewModelScope.launch {
            timerJob?.cancel()
            voice.stopSpeaking()
            voice.stopListening()
            voice.endAudio()
            if (sid != null) {
                api.hangup(sid)
            }
            ended = Ended(message = "Call ended")
            screen = Screen.ENDED
        }
    }

    fun toggleMute() {
        muted = !muted
        if (muted) {
            voice.stopListening()
        } else {
            if (screen == Screen.IN_CALL && callStatus != "Speaking" && callStatus != "Thinking" && callStatus != "Ringing") {
                startListening()
            }
        }
    }

    fun toggleSpeaker() {
        speaker = !speaker
        voice.setSpeaker(speaker)
    }

    private fun saveBookingSession(sid: String) {
        try {
            val raw = prefs.getString("bookings", "[]") ?: "[]"
            val existing = JSONArray(raw)
            val updated = JSONArray()
            updated.put(sid)
            for (i in 0 until existing.length()) {
                val item = existing.optString(i)
                if (item != sid && item.isNotEmpty()) {
                    updated.put(item)
                }
            }
            prefs.edit().putString("bookings", updated.toString()).apply()
        } catch (_: Exception) {}
    }

    fun loadAppointments() {
        viewModelScope.launch {
            val raw = prefs.getString("bookings", "[]") ?: "[]"
            val arr = try { JSONArray(raw) } catch (_: Exception) { JSONArray() }
            val list = mutableListOf<Booking>()
            for (i in 0 until arr.length()) {
                val sid = arr.optString(i)
                if (sid.isNullOrBlank()) continue
                try {
                    val b = api.booking(sid)
                    if (b != null) {
                        list.add(b)
                    }
                } catch (_: Exception) {}
            }
            appointments = list
        }
    }

    override fun onCleared() {
        super.onCleared()
        timerJob?.cancel()
        voice.release()
    }
}
