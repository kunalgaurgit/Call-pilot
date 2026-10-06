package com.callpilot.app

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.net.URL
import java.time.LocalDate
import java.time.format.TextStyle
import java.util.Locale

val Icons.Filled.Call: ImageVector
    get() {
        if (_callVector != null) {
            return _callVector!!
        }
        _callVector = ImageVector.Builder(
            name = "Filled.Call",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(fill = SolidColor(Color.Black)) {
                moveTo(20.01f, 15.38f)
                curveToRelative(-1.23f, 0f, -2.42f, -0.2f, -3.53f, -0.56f)
                curveToRelative(-0.35f, -0.12f, -0.74f, -0.03f, -1.02f, 0.24f)
                lineToRelative(-2.2f, 2.2f)
                curveToRelative(-2.83f, -1.44f, -5.15f, -3.75f, -6.59f, -6.59f)
                lineToRelative(2.2f, -2.21f)
                curveToRelative(0.28f, -0.27f, 0.36f, -0.66f, 0.25f, -1.01f)
                curveTo(8.7f, 6.34f, 8.5f, 5.16f, 8.5f, 3.93f)
                curveToRelative(0f, -0.53f, -0.45f, -0.93f, -0.93f, -0.93f)
                horizontalLineTo(4.06f)
                curveToRelative(-0.53f, 0f, -1.06f, 0.44f, -1.06f, 0.98f)
                curveTo(3f, 13.57f, 10.43f, 21f, 19.95f, 21f)
                curveToRelative(0.54f, 0f, 0.95f, -0.52f, 0.95f, -1.05f)
                verticalLineToRelative(-3.54f)
                curveToRelative(0f, -0.53f, -0.44f, -1.03f, -0.89f, -1.03f)
                close()
            }
        }.build()
        return _callVector!!
    }
private var _callVector: ImageVector? = null

val CallPilotDarkScheme = darkColorScheme(
    primary = Color(0xFF16A34A),
    onPrimary = Color.White,
    primaryContainer = Color(0xFF14532D),
    onPrimaryContainer = Color(0xFFDCFCE7),
    background = Color(0xFF0F172A),
    onBackground = Color(0xFFF8FAFC),
    surface = Color(0xFF1E293B),
    onSurface = Color(0xFFF8FAFC),
    surfaceVariant = Color(0xFF334155),
    onSurfaceVariant = Color(0xFF94A3B8),
    error = Color(0xFFDC2626),
    onError = Color.White
)

@Composable
fun CallPilotTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = CallPilotDarkScheme,
        content = content
    )
}

fun formatSpokenDate(dateStr: String): String {
    return try {
        val parsed = LocalDate.parse(dateStr.trim())
        val dayOfWeek = parsed.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.ENGLISH)
        val day = parsed.dayOfMonth
        val month = parsed.month.getDisplayName(TextStyle.FULL, Locale.ENGLISH)
        "$dayOfWeek $day $month"
    } catch (_: Exception) {
        dateStr
    }
}

fun formatFullPdfUrl(serverUrl: String, pdfUrl: String): String {
    val cleanServer = serverUrl.trim().trimEnd('/')
    val cleanPath = if (pdfUrl.startsWith("/")) pdfUrl else "/$pdfUrl"
    return "$cleanServer$cleanPath"
}

@Composable
fun DialerScreen(viewModel: CallViewModel, onCallClick: () -> Unit) {
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(top = 32.dp)
            ) {
                Text(
                    text = "CityCare Hospital",
                    style = MaterialTheme.typography.headlineLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Appointment Helpline",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(modifier = Modifier.height(24.dp))

                val serverText = when (viewModel.serverState) {
                    "Searching" -> "Searching..."
                    "Connected" -> {
                        val host = try {
                            URL(viewModel.serverUrl).host
                        } catch (_: Exception) {
                            viewModel.serverUrl
                        }
                        "Connected - $host"
                    }
                    else -> "Server not found - tap to retry"
                }

                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = when (viewModel.serverState) {
                        "Connected" -> Color(0xFF14532D)
                        "Searching" -> MaterialTheme.colorScheme.surfaceVariant
                        else -> Color(0xFF451A1A)
                    },
                    modifier = Modifier
                        .clip(RoundedCornerShape(16.dp))
                        .clickable(enabled = viewModel.serverState != "Searching") {
                            viewModel.retrySearch()
                        }
                ) {
                    Text(
                        text = serverText,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = when (viewModel.serverState) {
                            "Connected" -> Color(0xFFDCFCE7)
                            "Searching" -> MaterialTheme.colorScheme.onSurfaceVariant
                            else -> Color(0xFFFCA5A5)
                        }
                    )
                }
            }

            Column(
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Button(
                    onClick = onCallClick,
                    modifier = Modifier.size(96.dp),
                    shape = CircleShape,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF16A34A)
                    ),
                    contentPadding = PaddingValues(0.dp)
                ) {
                    Icon(
                        imageVector = Icons.Filled.Call,
                        contentDescription = "Call",
                        modifier = Modifier.size(48.dp),
                        tint = Color.White
                    )
                }

                Spacer(modifier = Modifier.height(36.dp))

                Row(
                    horizontalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    TextButton(onClick = {
                        viewModel.loadAppointments()
                        viewModel.screen = Screen.APPOINTMENTS
                    }) {
                        Text(
                            text = "My appointments",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodyLarge
                        )
                    }
                    TextButton(onClick = {
                        viewModel.screen = Screen.SETTINGS
                    }) {
                        Text(
                            text = "Settings",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodyLarge
                        )
                    }
                }
            }

            Text(
                text = "Demo project - not a real hospital",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                modifier = Modifier.padding(bottom = 16.dp)
            )
        }
    }
}

@Composable
fun InCallScreen(viewModel: CallViewModel) {
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(top = 24.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(80.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.surfaceVariant),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "CC",
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                        color = Color.White
                    )
                }
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "CityCare Hospital",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground
                )
                Spacer(modifier = Modifier.height(8.dp))
                val minutes = viewModel.seconds / 60
                val secs = viewModel.seconds % 60
                val timerText = "%02d:%02d".format(minutes, secs)
                Text(
                    text = "${viewModel.callStatus} • $timerText",
                    style = MaterialTheme.typography.titleMedium,
                    color = if (viewModel.callStatus == "Speaking" || viewModel.callStatus == "Listening") {
                        Color(0xFF16A34A)
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    }
                )
            }

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                if (viewModel.agentLine.isNotEmpty()) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        shape = RoundedCornerShape(16.dp)
                    ) {
                        Text(
                            text = viewModel.agentLine,
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.padding(16.dp),
                            textAlign = TextAlign.Center
                        )
                    }
                }
                if (viewModel.callerLine.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = "You: ${viewModel.callerLine}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center
                    )
                }
            }

            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(bottom = 24.dp)
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(32.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Button(
                        onClick = { viewModel.toggleMute() },
                        modifier = Modifier.size(56.dp),
                        shape = CircleShape,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (viewModel.muted) Color(0xFFDC2626) else MaterialTheme.colorScheme.surfaceVariant
                        ),
                        contentPadding = PaddingValues(0.dp)
                    ) {
                        Text(
                            text = if (viewModel.muted) "Unmute" else "Mute",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                    }

                    Button(
                        onClick = { viewModel.toggleSpeaker() },
                        modifier = Modifier.size(56.dp),
                        shape = CircleShape,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (viewModel.speaker) Color(0xFF16A34A) else MaterialTheme.colorScheme.surfaceVariant
                        ),
                        contentPadding = PaddingValues(0.dp)
                    ) {
                        Text(
                            text = if (viewModel.speaker) "Speaker" else "Ear",
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                    }
                }

                Spacer(modifier = Modifier.height(32.dp))

                Button(
                    onClick = { viewModel.endCall() },
                    modifier = Modifier.size(72.dp),
                    shape = CircleShape,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFFDC2626)
                    ),
                    contentPadding = PaddingValues(0.dp)
                ) {
                    Icon(
                        imageVector = Icons.Filled.Call,
                        contentDescription = "End Call",
                        modifier = Modifier
                            .size(36.dp)
                            .rotate(135f),
                        tint = Color.White
                    )
                }
            }
        }
    }
}

@Composable
fun EndedScreen(viewModel: CallViewModel, onDone: () -> Unit) {
    val context = LocalContext.current
    val ended = viewModel.ended

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            if (!ended.bookingId.isNullOrEmpty()) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = "Appointment confirmed",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF16A34A)
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = ended.bookingId,
                            style = MaterialTheme.typography.headlineLarge,
                            fontWeight = FontWeight.ExtraBold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        Spacer(modifier = Modifier.height(16.dp))

                        if (!ended.doctor.isNullOrEmpty()) {
                            Text(
                                text = "Doctor: ${ended.doctor}",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                        }
                        if (!ended.department.isNullOrEmpty()) {
                            Text(
                                text = "Department: ${ended.department}",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        if (!ended.date.isNullOrEmpty()) {
                            Text(
                                text = "Date: ${formatSpokenDate(ended.date)}",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                        }
                        if (!ended.time.isNullOrEmpty()) {
                            Text(
                                text = "Time: ${ended.time}",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                        }
                        if (!ended.branch.isNullOrEmpty()) {
                            Text(
                                text = "Branch: ${ended.branch}",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }

                        if (!ended.pdfUrl.isNullOrEmpty()) {
                            Spacer(modifier = Modifier.height(20.dp))
                            Button(
                                onClick = {
                                    val fullUrl = formatFullPdfUrl(viewModel.serverUrl, ended.pdfUrl)
                                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(fullUrl))
                                    try {
                                        context.startActivity(intent)
                                    } catch (_: Exception) {}
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF16A34A))
                            ) {
                                Text("Open booking PDF")
                            }
                        }
                    }
                }
            } else if (ended.emergency) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF451A1A)),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = "Emergency Helpline",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFFCA5A5)
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = ended.message.ifEmpty { "Please dial 108 immediately." },
                            style = MaterialTheme.typography.bodyLarge,
                            color = Color.White,
                            textAlign = TextAlign.Center
                        )
                    }
                }
            } else {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = ended.message.ifEmpty { "Call ended" },
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface,
                            textAlign = TextAlign.Center
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(32.dp))

            Button(
                onClick = onDone,
                modifier = Modifier
                    .fillMaxWidth(0.5f)
                    .height(48.dp),
                shape = RoundedCornerShape(24.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
            ) {
                Text("Done", color = Color.White)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppointmentsScreen(viewModel: CallViewModel, onBack: () -> Unit) {
    val context = LocalContext.current

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text("My appointments", color = MaterialTheme.colorScheme.onBackground) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = MaterialTheme.colorScheme.onBackground
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background)
            )
        }
    ) { innerPadding ->
        if (viewModel.appointments.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "No appointments yet",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(viewModel.appointments) { appt ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        shape = RoundedCornerShape(16.dp)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = appt.bookingId,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = Color(0xFF16A34A)
                                )
                                if (appt.pdfUrl.isNotEmpty()) {
                                    OutlinedButton(
                                        onClick = {
                                            val fullUrl = formatFullPdfUrl(viewModel.serverUrl, appt.pdfUrl)
                                            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(fullUrl))
                                            try {
                                                context.startActivity(intent)
                                            } catch (_: Exception) {}
                                        },
                                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                                    ) {
                                        Text("PDF", fontSize = 12.sp)
                                    }
                                }
                            }
                            Spacer(modifier = Modifier.height(8.dp))
                            if (appt.doctor.isNotEmpty()) {
                                Text(
                                    text = "Doctor: ${appt.doctor}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                            }
                            if (appt.department.isNotEmpty()) {
                                Text(
                                    text = "Department: ${appt.department}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            if (appt.appointmentDate.isNotEmpty()) {
                                Text(
                                    text = "Date: ${formatSpokenDate(appt.appointmentDate)}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                            }
                            if (appt.appointmentTime.isNotEmpty()) {
                                Text(
                                    text = "Time: ${appt.appointmentTime}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                            }
                            if (appt.hospitalBranch.isNotEmpty()) {
                                Text(
                                    text = "Branch: ${appt.hospitalBranch}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(viewModel: CallViewModel, onBack: () -> Unit) {
    var urlText by remember { mutableStateOf(viewModel.serverUrl) }

    LaunchedEffect(viewModel.serverUrl) {
        urlText = viewModel.serverUrl
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text("Settings", color = MaterialTheme.colorScheme.onBackground) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = MaterialTheme.colorScheme.onBackground
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background)
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(24.dp)
        ) {
            OutlinedTextField(
                value = urlText,
                onValueChange = { urlText = it },
                label = { Text("Server URL") },
                placeholder = { Text("http://192.168.137.1:8001") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFF16A34A),
                    focusedLabelColor = Color(0xFF16A34A),
                    cursorColor = Color(0xFF16A34A)
                )
            )

            Spacer(modifier = Modifier.height(16.dp))

            Text(
                text = "Status: ${viewModel.serverState}",
                style = MaterialTheme.typography.bodyMedium,
                color = when (viewModel.serverState) {
                    "Connected" -> Color(0xFF16A34A)
                    "Searching" -> MaterialTheme.colorScheme.onSurfaceVariant
                    else -> Color(0xFFDC2626)
                }
            )

            Spacer(modifier = Modifier.height(24.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                OutlinedButton(
                    onClick = { viewModel.retrySearch() },
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Find automatically")
                }

                Button(
                    onClick = { viewModel.saveServerUrl(urlText) },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF16A34A))
                ) {
                    Text("Save")
                }
            }
        }
    }
}
