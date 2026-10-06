package com.callpilot.app

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale
import java.util.UUID

class Voice(private val ctx: Context) {

    private val mainHandler = Handler(Looper.getMainLooper())
    private val audioManager = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var pendingSpeak: Pair<String, () -> Unit>? = null
    @Volatile private var currentUtteranceId: String? = null
    @Volatile private var currentOnDone: (() -> Unit)? = null

    private var recognizer: SpeechRecognizer? = null

    init {
        tts = TextToSpeech(ctx) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val localeIn = Locale("en", "IN")
                val langResult = tts?.setLanguage(localeIn)
                if (langResult == TextToSpeech.LANG_MISSING_DATA || langResult == TextToSpeech.LANG_NOT_SUPPORTED) {
                    tts?.language = Locale.ENGLISH
                }
                val audioAttrs = AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
                tts?.setAudioAttributes(audioAttrs)
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}

                    override fun onDone(utteranceId: String?) {
                        if (utteranceId != null && utteranceId == currentUtteranceId) {
                            val cb = currentOnDone
                            currentOnDone = null
                            currentUtteranceId = null
                            if (cb != null) {
                                mainHandler.post(cb)
                            }
                        }
                    }

                    override fun onError(utteranceId: String?) {
                        if (utteranceId != null && utteranceId == currentUtteranceId) {
                            val cb = currentOnDone
                            currentOnDone = null
                            currentUtteranceId = null
                            if (cb != null) {
                                mainHandler.post(cb)
                            }
                        }
                    }
                })
                ttsReady = true
                val pending = pendingSpeak
                pendingSpeak = null
                if (pending != null) {
                    speak(pending.first, pending.second)
                }
            }
        }
    }

    fun speak(text: String, onDone: () -> Unit) {
        stopListening()
        stopSpeaking()
        if (!ttsReady) {
            pendingSpeak = Pair(text, onDone)
            return
        }
        val utteranceId = UUID.randomUUID().toString()
        currentUtteranceId = utteranceId
        currentOnDone = onDone
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, utteranceId)
    }

    fun stopSpeaking() {
        pendingSpeak = null
        currentOnDone = null
        currentUtteranceId = null
        try {
            tts?.stop()
        } catch (_: Exception) {}
    }

    fun listen(onText: (String) -> Unit, onMiss: () -> Unit, onFatal: (String) -> Unit) {
        mainHandler.post {
            if (!SpeechRecognizer.isRecognitionAvailable(ctx)) {
                onFatal("Speech recognition not available on this phone")
                return@post
            }
            stopListening()
            val r = SpeechRecognizer.createSpeechRecognizer(ctx)
            recognizer = r
            r.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}

                override fun onError(error: Int) {
                    stopListening()
                    when (error) {
                        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> {
                            onFatal("Microphone permission denied")
                        }
                        SpeechRecognizer.ERROR_NO_MATCH,
                        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> {
                            onMiss()
                        }
                        else -> {
                            onMiss()
                        }
                    }
                }

                override fun onResults(results: Bundle?) {
                    stopListening()
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    val text = matches?.firstOrNull()?.trim()
                    if (!text.isNullOrEmpty()) {
                        onText(text)
                    } else {
                        onMiss()
                    }
                }

                override fun onPartialResults(partialResults: Bundle?) {}
                override fun onEvent(eventType: Int, params: Bundle?) {}
            })

            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
                putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, false)
            }
            try {
                r.startListening(intent)
            } catch (_: Exception) {
                onMiss()
            }
        }
    }

    fun stopListening() {
        mainHandler.post {
            try {
                recognizer?.stopListening()
                recognizer?.cancel()
                recognizer?.destroy()
            } catch (_: Exception) {}
            recognizer = null
        }
    }

    fun setSpeaker(on: Boolean) {
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val targetType = if (on) AudioDeviceInfo.TYPE_BUILTIN_SPEAKER else AudioDeviceInfo.TYPE_BUILTIN_EARPIECE
            val device = audioManager.availableCommunicationDevices.firstOrNull { it.type == targetType }
            if (device != null) {
                audioManager.setCommunicationDevice(device)
            }
        } else {
            @Suppress("DEPRECATION")
            audioManager.isSpeakerphoneOn = on
        }
    }

    fun endAudio() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            audioManager.clearCommunicationDevice()
        } else {
            @Suppress("DEPRECATION")
            audioManager.isSpeakerphoneOn = false
        }
        audioManager.mode = AudioManager.MODE_NORMAL
    }

    fun release() {
        stopListening()
        stopSpeaking()
        endAudio()
        tts?.shutdown()
        tts = null
    }
}
