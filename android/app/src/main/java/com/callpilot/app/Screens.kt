package com.callpilot.app

import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.basicMarquee
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle as UiTextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.net.URL
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
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

// Original Call Pilot dark theme: slate background, rounded cards, green primary.
private val Desk = Color(0xFF0F172A)
private val PanelBg = Color(0xFF1E293B)
private val Shadow = Color(0xFF334155)
private val Well = Color(0xFF0B1220)
private val Navy = Color(0xFF3B82F6)
private val Slate = Color(0xFF64748B)
private val Ink = Color(0xFFF8FAFC)
private val Muted = Color(0xFF94A3B8)
private val Green = Color(0xFF16A34A)
private val Red = Color(0xFFDC2626)
private val Amber = Color(0xFFF59E0B)
private val Mono = FontFamily.Monospace
private val Round = RoundedCornerShape(14.dp)
private val RoundSmall = RoundedCornerShape(10.dp)

val CallPilotDarkScheme = darkColorScheme(
    primary = Green,
    onPrimary = Color.White,
    primaryContainer = Color(0xFF14532D),
    onPrimaryContainer = Color(0xFFDCFCE7),
    background = Desk,
    onBackground = Ink,
    surface = PanelBg,
    onSurface = Ink,
    surfaceVariant = Shadow,
    onSurfaceVariant = Muted,
    error = Red,
    onError = Color.White
)

@Composable
fun CallPilotTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = CallPilotDarkScheme, content = content)
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

private fun openUrl(context: android.content.Context, url: String) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    } catch (_: Exception) {}
}

private val CONDITIONS = listOf(
    "C01 Common cold", "C02 Fever", "C03 Headache", "C04 Acidity", "C05 Loose motions",
    "C06 Muscle pain", "C07 Allergy / sneezing", "C08 Sore throat", "C09 Dry cough", "C10 Constipation"
)

private val HEALTH_TIPS = listOf(
    "Drink 8 to 10 glasses of water every day.",
    "Walk for 30 minutes daily - it lowers BP and sugar.",
    "Wash hands for 20 seconds before every meal.",
    "Sleep 7 to 8 hours; screens off 30 minutes before bed.",
    "Eat one seasonal fruit and one green vegetable daily.",
    "Never take antibiotics without a doctor's prescription.",
    "Haldi doodh at night soothes a sore throat."
)

// Labels for the live case sheet, in consultation order (server field names).
private val CASE_FIELDS = listOf(
    "symptoms" to "Chief complaint",
    "duration_days" to "Duration (days)",
    "symptom_details" to "History",
    "associated_symptoms" to "Other symptoms",
    "tried_so_far" to "Tried so far",
    "severity" to "Severity (AI)",
    "patient_name" to "Patient name",
    "age" to "Age",
    "gender" to "Gender",
    "pregnant" to "Pregnant",
    "allergies" to "Allergies",
    "current_medicines" to "Current meds",
    "condition" to "Provisional Dx"
)

// ---------- building blocks ----------

@Composable
private fun Bevel(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    Box(modifier.clip(RoundSmall).border(1.dp, Shadow, RoundSmall), content = content)
}

@Composable
private fun TitleBar(text: String, right: String = "", onBack: (() -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (onBack != null) {
            RetroButton("< Back", onClick = onBack, fontSize = 12.sp, height = 34.dp)
            Spacer(Modifier.width(10.dp))
        }
        Text(text, color = Ink, fontWeight = FontWeight.Bold, fontSize = 18.sp, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (right.isNotEmpty()) {
            Text(right, color = Muted, fontSize = 12.sp, fontFamily = Mono,
                modifier = Modifier.clip(CircleShape).background(PanelBg).padding(horizontal = 10.dp, vertical = 4.dp))
        }
    }
}

@Composable
private fun Panel(title: String, modifier: Modifier = Modifier, accent: Color = Navy, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier
            .padding(vertical = 4.dp)
            .fillMaxWidth()
            .clip(Round)
            .background(PanelBg)
            .border(1.dp, Shadow, Round)
            .padding(12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(accent, CircleShape))
            Spacer(Modifier.width(6.dp))
            Text(title.uppercase(), color = accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
        }
        Spacer(Modifier.height(8.dp))
        content()
    }
}

@Composable
private fun KV(label: String, value: String, valueColor: Color = Ink) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(label, fontSize = 12.sp, color = Muted, modifier = Modifier.width(112.dp))
        Text(value.ifEmpty { "-" }, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = if (value.isEmpty()) Slate else valueColor)
    }
}

@Composable
private fun RetroButton(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = Shadow,
    textColor: Color = Ink,
    fontSize: TextUnit = 13.sp,
    height: Dp = 44.dp,
    enabled: Boolean = true,
    onClick: () -> Unit
) {
    Box(
        modifier
            .height(height)
            .clip(RoundSmall)
            .background(if (enabled) color else PanelBg)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 10.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(text, color = if (enabled) textColor else Slate, fontSize = fontSize, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center, maxLines = 2)
    }
}

@Composable
private fun Led(label: String, on: Boolean, color: Color, modifier: Modifier = Modifier) {
    Row(
        modifier.clip(CircleShape).background(if (on) color.copy(alpha = 0.18f) else PanelBg).padding(horizontal = 6.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Box(Modifier.size(7.dp).background(if (on) color else Shadow, CircleShape))
        Spacer(Modifier.width(4.dp))
        Text(label, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, color = if (on) Ink else Slate)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun Ticker(text: String) {
    Text(
        text,
        color = Color(0xFFFDE68A),
        fontSize = 12.sp,
        maxLines = 1,
        modifier = Modifier
            .padding(horizontal = 12.dp)
            .fillMaxWidth()
            .clip(CircleShape)
            .background(Color(0xFF422006))
            .padding(vertical = 5.dp)
            .basicMarquee(iterations = Int.MAX_VALUE)
    )
}

@Composable
private fun StatusStrip(text: String) {
    Text(text, fontSize = 10.sp, color = Slate, maxLines = 1, overflow = TextOverflow.Ellipsis,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp))
}

@Composable
private fun clock(pattern: String): String {
    var now by remember { mutableStateOf(LocalDateTime.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(1000)
            now = LocalDateTime.now()
        }
    }
    return now.format(DateTimeFormatter.ofPattern(pattern, Locale.ENGLISH))
}

@Composable
private fun MedTable(meds: List<Medicine>) {
    Column(Modifier.fillMaxWidth().clip(RoundSmall).border(1.dp, Shadow, RoundSmall)) {
        Row(Modifier.background(Shadow).padding(6.dp)) {
            Text("MEDICINE", Modifier.weight(1.3f), fontSize = 9.sp, fontWeight = FontWeight.Bold)
            Text("DOSE / WHEN", Modifier.weight(1.7f), fontSize = 9.sp, fontWeight = FontWeight.Bold)
            Text("DAYS", Modifier.weight(0.5f), fontSize = 9.sp, fontWeight = FontWeight.Bold)
        }
        meds.forEach { m ->
            HorizontalDivider(color = Shadow, thickness = 0.5.dp)
            Row(Modifier.padding(6.dp)) {
                Text("${m.name} ${m.strength}".trim(), Modifier.weight(1.3f), fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                Text(listOf(m.dose, m.frequency).filter { it.isNotEmpty() }.joinToString(", "), Modifier.weight(1.7f), fontSize = 10.sp)
                Text(m.days, Modifier.weight(0.5f), fontSize = 10.sp, fontFamily = Mono)
            }
        }
    }
}

@Composable
private fun Bullets(items: List<String>) {
    items.forEach { Text("\u2022  $it", fontSize = 12.sp, color = Ink, modifier = Modifier.padding(vertical = 1.dp)) }
}

@Composable
private fun Screenful(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .background(Desk)
            .systemBarsPadding()
            .padding(top = 4.dp),
        content = content
    )
}

// ---------- screens ----------

@Composable
fun DialerScreen(viewModel: CallViewModel, onCallClick: () -> Unit) {
    val context = LocalContext.current
    val info = viewModel.serverInfo
    val ai = info?.optJSONObject("ai")
    val host = try { URL(viewModel.serverUrl).host } catch (_: Exception) { viewModel.serverUrl }
    val tip = HEALTH_TIPS[LocalDate.now().dayOfYear % HEALTH_TIPS.size]

    Screenful {
        TitleBar("AI DOCTOR :: TELE-CONSULTATION TERMINAL", "v${BuildConfig.VERSION_NAME}")
        Ticker("*** EMERGENCY? DIAL 108 ***   24x7 AI HEALTH CONSULTATION   ***   ALLOPATHY + AYURVEDA + HOMEOPATHY + GHARELU UPAY   ***   HINDI / ENGLISH SUPPORTED   ***   TIP: $tip   ***   COLLEGE DEMO - NOT A REAL DOCTOR   ***")
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp)) {
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Panel("System status", Modifier.weight(1.2f).fillMaxHeight()) {
                    KV("Server", when (viewModel.serverState) {
                        "Connected" -> "ONLINE"
                        "Searching" -> "SEARCHING.."
                        else -> "OFFLINE"
                    }, if (viewModel.serverState == "Connected") Green else Red)
                    KV("Host", if (viewModel.serverState == "Connected") host else "")
                    KV("AI engine", (ai?.optString("state") ?: "").uppercase(), if (ai?.optString("state") == "ok") Green else Amber)
                    KV("Mode", (info?.optString("mode") ?: "").uppercase())
                    KV("Model", info?.optString("model")?.substringBefore(",") ?: "")
                    KV("Active calls", info?.optInt("active_calls")?.toString() ?: "")
                }
                Panel("Clock", Modifier.weight(0.8f).fillMaxHeight(), accent = Slate) {
                    Text(clock("HH:mm:ss"), fontFamily = Mono, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Green,
                        modifier = Modifier.fillMaxWidth().clip(RoundSmall).background(Well).padding(6.dp), textAlign = TextAlign.Center)
                    Spacer(Modifier.height(4.dp))
                    Text(clock("EEE, dd MMM yyyy"), fontSize = 11.sp, fontFamily = Mono)
                    Text("OPD: 24 x 7", fontSize = 11.sp, fontFamily = Mono)
                    Text("Lang: EN / HI", fontSize = 11.sp, fontFamily = Mono)
                    Text("Device: ${Build.MODEL}", fontSize = 10.sp, fontFamily = Mono, color = Muted, maxLines = 1)
                }
            }

            Panel("Start consultation", accent = Green) {
                RetroButton("Start AI doctor consultation", Modifier.fillMaxWidth(), color = Green, textColor = Color.White, fontSize = 14.sp, height = 56.dp, onClick = onCallClick)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    RetroButton("MY PRESCRIPTIONS", Modifier.weight(1f), fontSize = 10.sp) {
                        viewModel.loadAppointments()
                        viewModel.screen = Screen.APPOINTMENTS
                    }
                    RetroButton("SETTINGS", Modifier.weight(1f), fontSize = 10.sp) { viewModel.screen = Screen.SETTINGS }
                }
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    RetroButton("EMERGENCY 108", Modifier.weight(1f), color = Red, textColor = Color.White, fontSize = 10.sp) {
                        try { context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:108"))) } catch (_: Exception) {}
                    }
                    RetroButton("RECONNECT SERVER", Modifier.weight(1f), fontSize = 10.sp, enabled = viewModel.serverState != "Searching") { viewModel.retrySearch() }
                }
            }

            Panel("Treatment systems available") {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("ALLOPATHY" to Color(0xFF60A5FA), "AYURVEDA" to Color(0xFF4ADE80), "HOMEOPATHY" to Color(0xFFC084FC), "GHARELU UPAY" to Amber).forEach { (name, c) ->
                        Text(name, color = c, fontSize = 9.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
                            modifier = Modifier.weight(1f).clip(RoundSmall).background(c.copy(alpha = 0.15f)).padding(vertical = 8.dp))
                    }
                }
            }

            Panel("Conditions handled (minor ailments)") {
                CONDITIONS.chunked(2).forEach { pair ->
                    Row {
                        pair.forEach { Text(it, Modifier.weight(1f), fontSize = 11.sp, fontFamily = Mono) }
                        if (pair.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
                Spacer(Modifier.height(3.dp))
                Text("Chest pain, breathlessness, fainting, bleeding -> call 108, not this line.", fontSize = 10.sp, color = Red, fontWeight = FontWeight.Bold)
            }

            Panel("How it works", accent = Slate) {
                listOf(
                    "1. Tap CALL and describe your problem (Hindi or English).",
                    "2. AI doctor takes your history like a real doctor.",
                    "3. Give name, age, gender and allergies.",
                    "4. Confirm the summary.",
                    "5. Get a PDF prescription: allopathic, Ayurvedic, homeopathic and home remedies."
                ).forEach { Text(it, fontSize = 11.sp) }
            }

            Panel("Health tip of the day", accent = Amber) {
                Text(tip, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            }
        }
        StatusStrip("READY | ${viewModel.serverState.uppercase()} | ${viewModel.serverUrl.ifEmpty { "no server" }} | (c) 2026 Call Pilot | Demo - not medical advice")
    }
}

@Composable
fun InCallScreen(viewModel: CallViewModel) {
    val status = viewModel.callStatus
    val sheet = viewModel.caseSheet
    val timer = "%02d:%02d".format(viewModel.seconds / 60, viewModel.seconds % 60)
    val stage = when {
        sheet.containsKey("condition") && sheet.containsKey("allergies") -> 4
        sheet.containsKey("patient_name") || sheet.containsKey("age") -> 3
        sheet.containsKey("symptom_details") || sheet.containsKey("associated_symptoms") -> 2
        sheet.containsKey("symptoms") -> 1
        else -> 0
    }
    val logScroll = rememberScrollState()
    LaunchedEffect(viewModel.log.size, viewModel.callerLine) { logScroll.animateScrollTo(logScroll.maxValue) }

    Screenful {
        TitleBar("CONSULTATION IN PROGRESS  * REC", timer)
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Led("MIC", status == "Listening", Green, Modifier.weight(1f))
            Led("AI", status == "Thinking", Amber, Modifier.weight(1f))
            Led("TTS", status == "Speaking", Color(0xFF38BDF8), Modifier.weight(1f))
            Led("NET", viewModel.serverState == "Connected", Green, Modifier.weight(1f))
            Led("MUTE", viewModel.muted, Red, Modifier.weight(1f))
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp)) {
            Panel("Consultation stage") {
                Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    listOf("COMPLAINT", "HISTORY", "PATIENT", "CONFIRM", "Rx").forEachIndexed { i, s ->
                        Text(s, fontSize = 8.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
                            color = if (i <= stage) Color.White else Muted,
                            modifier = Modifier.weight(1f).clip(RoundSmall).background(if (i < stage) Green else if (i == stage) Navy else Shadow).padding(vertical = 6.dp))
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Panel("Audio monitor", Modifier.weight(1f), accent = Slate) {
                    val levels = viewModel.micLevels
                    val wave = if (status == "Listening") Color(0xFF22C55E) else Shadow
                    Canvas(Modifier.fillMaxWidth().height(40.dp).clip(RoundSmall).background(Well)) {
                        val step = size.width / levels.size
                        levels.forEachIndexed { i, level ->
                            val half = maxOf(1f, level * size.height / 2)
                            val x = step * i + step / 2
                            drawLine(wave, Offset(x, center.y - half), Offset(x, center.y + half), step * 0.7f)
                        }
                    }
                    Text("STATUS: ${status.uppercase()}", fontSize = 10.sp, fontFamily = Mono, fontWeight = FontWeight.Bold)
                    Text("SPK: ${if (viewModel.speaker) "LOUD" else "EARPIECE"}", fontSize = 10.sp, fontFamily = Mono)
                }
                Panel("Patient", Modifier.weight(1f), accent = Slate) {
                    Text(sheet["patient_name"] ?: "UNREGISTERED", fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 1)
                    Text("${sheet["age"] ?: "--"} yrs / ${sheet["gender"] ?: "--"}", fontSize = 10.sp, fontFamily = Mono)
                    Text("Severity: ${(sheet["severity"] ?: "pending").uppercase()}", fontSize = 10.sp, fontFamily = Mono,
                        color = when (sheet["severity"]) { "severe" -> Red; "moderate" -> Amber; "mild" -> Green; else -> Muted })
                    Text("Fields: ${sheet.size}/${CASE_FIELDS.size}", fontSize = 10.sp, fontFamily = Mono)
                }
            }
            Panel("AI doctor says", accent = Green) {
                Text(viewModel.agentLine.ifEmpty { "Connecting..." }, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                if (viewModel.callerLine.isNotEmpty()) {
                    Spacer(Modifier.height(3.dp))
                    Text("YOU: ${viewModel.callerLine}", fontSize = 11.sp, color = Muted, fontFamily = Mono)
                }
            }
            Panel("Live case sheet") {
                CASE_FIELDS.forEach { (key, label) -> KV(label, sheet[key] ?: "") }
            }
            Panel("Transcript log", accent = Slate) {
                Column(Modifier.fillMaxWidth().height(150.dp).clip(RoundSmall).background(Well).verticalScroll(logScroll).padding(8.dp)) {
                    viewModel.log.forEach { (who, text) ->
                        Text("[$who] $text", fontSize = 10.sp, fontFamily = Mono, color = if (who == "AI") Color(0xFF4ADE80) else Color(0xFFFDE047))
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            RetroButton(if (viewModel.muted) "UNMUTE" else "MUTE", Modifier.weight(1f), color = if (viewModel.muted) Amber else Shadow,
                textColor = if (viewModel.muted) Color.White else Ink, height = 52.dp) { viewModel.toggleMute() }
            RetroButton(if (viewModel.speaker) "SPEAKER ON" else "SPEAKER", Modifier.weight(1f), color = if (viewModel.speaker) Navy else Shadow,
                textColor = if (viewModel.speaker) Color.White else Ink, height = 52.dp) { viewModel.toggleSpeaker() }
            Bevel(Modifier.weight(1.2f).height(52.dp)) {
                Row(Modifier.fillMaxSize().background(Red).clickable { viewModel.endCall() }, horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Call, contentDescription = "End call", tint = Color.White, modifier = Modifier.size(22.dp).rotate(135f))
                    Spacer(Modifier.width(4.dp))
                    Text("END CALL", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
fun EndedScreen(viewModel: CallViewModel, onDone: () -> Unit) {
    val context = LocalContext.current
    val ended = viewModel.ended
    val rx = ended.rx
    var autoOpened by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(ended.pdfUrl) {
        if (!autoOpened && !ended.pdfUrl.isNullOrEmpty()) {
            autoOpened = true
            openUrl(context, formatFullPdfUrl(viewModel.serverUrl, ended.pdfUrl))
        }
    }

    Screenful {
        TitleBar("CONSULTATION SUMMARY", "%02d:%02d".format(viewModel.seconds / 60, viewModel.seconds % 60))
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp)) {
            when {
                !ended.bookingId.isNullOrEmpty() -> {
                    val isRx = ended.bookingId.startsWith("RX-")
                    Panel(if (isRx) "Prescription issued" else "Appointment confirmed", accent = Green) {
                        Text(ended.bookingId, fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, fontFamily = Mono, color = Green)
                        if (rx != null && rx.condition.isNotEmpty()) KV("Assessment", rx.condition)
                        if (!ended.doctor.isNullOrEmpty()) KV("Doctor", ended.doctor)
                        if (!ended.department.isNullOrEmpty()) KV("Department", ended.department)
                        if (!ended.date.isNullOrEmpty()) KV("Date", formatSpokenDate(ended.date))
                        if (!ended.time.isNullOrEmpty()) KV("Time", ended.time)
                        if (!ended.branch.isNullOrEmpty()) KV("Branch", ended.branch)
                        KV("Issued", LocalDateTime.now().format(DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm a", Locale.ENGLISH)))
                    }
                    if (rx != null) {
                        if (rx.medicines.isNotEmpty()) Panel("1. Allopathic (OTC)", accent = Color(0xFF60A5FA)) { MedTable(rx.medicines) }
                        if (rx.ayurvedic.isNotEmpty()) Panel("2. Ayurvedic option", accent = Color(0xFF4ADE80)) { MedTable(rx.ayurvedic) }
                        if (rx.homeopathic.isNotEmpty()) Panel("3. Homeopathic option", accent = Color(0xFFC084FC)) { MedTable(rx.homeopathic) }
                        if (rx.homeRemedies.isNotEmpty()) Panel("4. Home remedies (gharelu upay)", accent = Amber) { Bullets(rx.homeRemedies) }
                        if (rx.advice.isNotEmpty()) Panel("Advice", accent = Slate) { Bullets(rx.advice) }
                        if (rx.seeDoctorIf.isNotEmpty()) Panel("See a doctor immediately if", accent = Red) { Bullets(rx.seeDoctorIf) }
                        Text("Take ONE system at a time. AI college demo - not a real prescription.", fontSize = 10.sp, color = Red, fontWeight = FontWeight.Bold, modifier = Modifier.padding(4.dp))
                    }
                }
                ended.emergency -> Panel("!!! Emergency !!!", accent = Red) {
                    Text(ended.message.ifEmpty { "Please dial 108 immediately." }, fontSize = 14.sp, fontWeight = FontWeight.Bold, color = Red)
                    Spacer(Modifier.height(8.dp))
                    RetroButton("DIAL 108 NOW", Modifier.fillMaxWidth(), color = Red, textColor = Color.White, height = 48.dp) {
                        try { context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:108"))) } catch (_: Exception) {}
                    }
                }
                else -> Panel("Call status", accent = Slate) {
                    Text(ended.message.ifEmpty { "Call ended" }, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                }
            }
            if (viewModel.caseSheet.isNotEmpty()) {
                Panel("Case sheet") {
                    CASE_FIELDS.filter { viewModel.caseSheet.containsKey(it.first) }.forEach { (k, label) -> KV(label, viewModel.caseSheet[k] ?: "") }
                }
            }
            if (viewModel.log.isNotEmpty()) {
                Panel("Call transcript (${viewModel.log.size} lines)", accent = Slate) {
                    viewModel.log.forEach { (who, text) -> Text("[$who] $text", fontSize = 10.sp, fontFamily = Mono) }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (!ended.pdfUrl.isNullOrEmpty()) {
                RetroButton("OPEN PDF", Modifier.weight(1f), color = Green, textColor = Color.White, height = 48.dp) {
                    openUrl(context, formatFullPdfUrl(viewModel.serverUrl, ended.pdfUrl))
                }
            }
            RetroButton("DONE", Modifier.weight(1f), height = 48.dp, onClick = onDone)
        }
    }
}

@Composable
fun AppointmentsScreen(viewModel: CallViewModel, onBack: () -> Unit) {
    val context = LocalContext.current
    Screenful {
        TitleBar("MY PRESCRIPTIONS / RECORDS", "${viewModel.appointments.size} found", onBack = onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp)) {
            if (viewModel.appointments.isEmpty()) {
                Panel("No records") { Text("No prescriptions yet. Complete a consultation to see it here.", fontSize = 12.sp) }
            }
            viewModel.appointments.forEachIndexed { i, appt ->
                Panel("#${i + 1}  ${appt.bookingId}", accent = if (appt.bookingId.startsWith("RX-")) Green else Navy) {
                    KV("Patient", appt.patientName)
                    KV("Age / Gender", "${appt.age} / ${appt.gender}")
                    KV("Complaint", appt.symptoms)
                    appt.rx?.let { rx ->
                        KV("Assessment", rx.condition)
                        KV("Allopathic", rx.medicines.joinToString { it.name })
                        KV("Ayurvedic", rx.ayurvedic.joinToString { it.name })
                        KV("Homeopathic", rx.homeopathic.joinToString { it.name })
                    }
                    if (appt.doctor.isNotEmpty()) KV("Doctor", appt.doctor)
                    if (appt.appointmentDate.isNotEmpty()) KV("Date", "${formatSpokenDate(appt.appointmentDate)} ${appt.appointmentTime}")
                    KV("Created", appt.createdAt.take(16).replace("T", " "))
                    if (appt.pdfUrl.isNotEmpty()) {
                        Spacer(Modifier.height(4.dp))
                        RetroButton("VIEW PDF", Modifier.fillMaxWidth(), height = 32.dp, fontSize = 11.sp) {
                            openUrl(context, formatFullPdfUrl(viewModel.serverUrl, appt.pdfUrl))
                        }
                    }
                }
            }
        }
        StatusStrip("RECORDS STORED ON SERVER ${viewModel.serverUrl}")
    }
}

@Composable
fun SettingsScreen(viewModel: CallViewModel, onBack: () -> Unit) {
    var urlText by remember { mutableStateOf(viewModel.serverUrl) }
    LaunchedEffect(viewModel.serverUrl) { urlText = viewModel.serverUrl }

    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var updateMsg by remember { mutableStateOf("Version ${BuildConfig.VERSION_NAME}") }
    var update by remember { mutableStateOf<AppUpdate?>(null) }
    var apkFile by remember { mutableStateOf<java.io.File?>(null) }
    var busy by remember { mutableStateOf(false) }

    Screenful {
        TitleBar("SETTINGS / CONTROL PANEL", onBack = onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp)) {
            Panel("Server connection") {
                Text("Server URL:", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                Bevel(Modifier.fillMaxWidth()) {
                    BasicTextField(
                        value = urlText,
                        onValueChange = { urlText = it },
                        singleLine = true,
                        textStyle = UiTextStyle(fontFamily = Mono, fontSize = 14.sp, color = Ink),
                        cursorBrush = SolidColor(Green),
                        modifier = Modifier.fillMaxWidth().background(Desk).padding(10.dp)
                    )
                }
                Text("e.g. http://192.168.137.1:8001", fontSize = 10.sp, color = Muted)
                Spacer(Modifier.height(4.dp))
                KV("Status", viewModel.serverState.uppercase(), when (viewModel.serverState) {
                    "Connected" -> Green
                    "Searching" -> Amber
                    else -> Red
                })
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    RetroButton("FIND AUTOMATICALLY", Modifier.weight(1f), fontSize = 10.sp) { viewModel.retrySearch() }
                    RetroButton("SAVE", Modifier.weight(1f), color = Green, textColor = Color.White) { viewModel.saveServerUrl(urlText) }
                }
            }

            Panel("Software update", accent = Slate) {
                Text(updateMsg, fontSize = 12.sp, fontFamily = Mono)
                Spacer(Modifier.height(8.dp))
                RetroButton(
                    when {
                        apkFile != null -> "INSTALL UPDATE"
                        update != null -> "DOWNLOAD AND INSTALL"
                        else -> "CHECK FOR UPDATES"
                    },
                    Modifier.fillMaxWidth(),
                    enabled = !busy
                ) {
                    val ready = apkFile
                    val found = update
                    when {
                        // Downloaded already: retry install (e.g. after allowing "install unknown apps")
                        ready != null -> if (!installUpdate(context, ready)) updateMsg = "Allow installs from Call Pilot, then tap Install"
                        found != null -> scope.launch {
                            busy = true
                            try {
                                val file = downloadUpdate(context, found) { updateMsg = "Downloading ${found.versionName}... $it%" }
                                apkFile = file
                                updateMsg = if (installUpdate(context, file)) "Installing ${found.versionName}..."
                                else "Allow installs from Call Pilot, then tap Install"
                            } catch (e: Exception) {
                                updateMsg = "Download failed: ${e.message ?: "network error"}"
                            }
                            busy = false
                        }
                        else -> scope.launch {
                            busy = true
                            updateMsg = "Checking for updates..."
                            updateMsg = try {
                                update = checkForUpdate()
                                update?.let { "Version ${it.versionName} available" } ?: "Up to date (${BuildConfig.VERSION_NAME})"
                            } catch (e: Exception) {
                                "Update check failed - no internet?"
                            }
                            busy = false
                        }
                    }
                }
            }

            Panel("About this device", accent = Slate) {
                KV("App", "Call Pilot AI Doctor")
                KV("Version", "${BuildConfig.VERSION_NAME} (build ${BuildConfig.VERSION_CODE})")
                KV("Device", "${Build.MANUFACTURER} ${Build.MODEL}")
                KV("Android", "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
                KV("Speech", "Google speech, en-IN")
                KV("Server", viewModel.serverUrl)
            }
        }
        StatusStrip("CONTROL PANEL | ${viewModel.serverState.uppercase()}")
    }
}
