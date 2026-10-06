package com.callpilot.app

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import android.os.Bundle
import android.os.PowerManager
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.core.content.ContextCompat

class MainActivity : ComponentActivity() {

    private val viewModel: CallViewModel by viewModels()
    private var proximityWakeLock: PowerManager.WakeLock? = null
    private var pendingCallAction: (() -> Unit)? = null

    private val recordAudioPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            pendingCallAction?.invoke()
        } else {
            Toast.makeText(this, "Microphone permission required for calls", Toast.LENGTH_SHORT).show()
        }
        pendingCallAction = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            CallPilotTheme {
                // Back from IN_CALL does nothing (must press End), from other screens -> DIALER
                BackHandler(enabled = true) {
                    when (viewModel.screen) {
                        Screen.IN_CALL -> {
                            // Do nothing per brief
                        }
                        Screen.DIALER -> {
                            finish()
                        }
                        else -> {
                            viewModel.screen = Screen.DIALER
                        }
                    }
                }

                // Proximity sensor, screen-on, and voice volume control stream
                LaunchedEffect(viewModel.screen) {
                    updateCallHardwareState(viewModel.screen == Screen.IN_CALL)
                }

                when (viewModel.screen) {
                    Screen.DIALER -> DialerScreen(
                        viewModel = viewModel,
                        onCallClick = {
                            requestAudioPermissionAndCall {
                                viewModel.call()
                            }
                        }
                    )
                    Screen.IN_CALL -> InCallScreen(viewModel = viewModel)
                    Screen.ENDED -> EndedScreen(
                        viewModel = viewModel,
                        onDone = { viewModel.screen = Screen.DIALER }
                    )
                    Screen.APPOINTMENTS -> AppointmentsScreen(
                        viewModel = viewModel,
                        onBack = { viewModel.screen = Screen.DIALER }
                    )
                    Screen.SETTINGS -> SettingsScreen(
                        viewModel = viewModel,
                        onBack = { viewModel.screen = Screen.DIALER }
                    )
                }
            }
        }
    }

    private fun requestAudioPermissionAndCall(action: () -> Unit) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            action()
        } else {
            pendingCallAction = action
            recordAudioPermission.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun updateCallHardwareState(inCall: Boolean) {
        if (inCall) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            volumeControlStream = AudioManager.STREAM_VOICE_CALL
            if (proximityWakeLock == null) {
                val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
                if (pm.isWakeLockLevelSupported(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK)) {
                    proximityWakeLock = pm.newWakeLock(
                        PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK,
                        "CallPilot:ProximityWakeLock"
                    )
                }
            }
            if (proximityWakeLock?.isHeld == false) {
                try {
                    proximityWakeLock?.acquire(2 * 60 * 60 * 1000L)
                } catch (_: Exception) {}
            }
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            volumeControlStream = AudioManager.USE_DEFAULT_STREAM_TYPE
            if (proximityWakeLock?.isHeld == true) {
                try {
                    proximityWakeLock?.release()
                } catch (_: Exception) {}
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (proximityWakeLock?.isHeld == true) {
            try {
                proximityWakeLock?.release()
            } catch (_: Exception) {}
        }
    }
}
