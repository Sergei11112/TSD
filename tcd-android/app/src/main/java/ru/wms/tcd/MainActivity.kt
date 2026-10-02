package ru.wms.tcd

import android.annotation.SuppressLint
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Тонкий клиент ТСД: WebView с веб-интерфейсом /static/terminal.html
 * + нативный перехват сканера (Broadcast Intents и клавиатурный эмулятор).
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var settingsPanel: View
    private lateinit var urlInput: EditText
    private lateinit var statusText: TextView
    private var serverUrl: String = ""

    // Действия сканеров различных производителей ТСД
    private val scanActions = listOf(
        "android.intent.action.SCANRESULT",          // Honeywell / generic
        "com.symbol.datawedge.api.ACTION",           // Zebra DataWedge
        "com.honeywell.scaneroutput.action",         // Honeywell
        "android.intent.action.SCAN_RESULT",
        "com.android.server.scannerservice.broadcast"
    )

    private val scanReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val code = extractCode(intent) ?: return
            runOnUiThread { deliverScan(code) }
        }
    }

    private fun extractCode(intent: Intent?): String? {
        if (intent == null) return null
        val keys = listOf("scannerdata", "com.symbol.datawedge.data_string",
                          "decode_data", "data", "barcode", "SCAN_DATA", "result")
        for (k in keys) {
            intent.getStringExtra(k)?.let { if (it.isNotBlank()) return it.trim() }
        }
        intent.extras?.keySet()?.forEach { key ->
            intent.getStringExtra(key)?.let { v ->
                if (v.isNotBlank() && (v.startsWith("WMS:") || v.length >= 3)) return v.trim()
            }
        }
        return null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webview)
        settingsPanel = findViewById(R.id.settings_panel)
        urlInput = findViewById(R.id.url_input)
        statusText = findViewById(R.id.status_text)

        serverUrl = getSharedPreferences("tcd", MODE_PRIVATE).getString("server_url", "") ?: ""
        urlInput.setText(serverUrl)

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.cacheMode = android.webkit.WebSettings.LOAD_NO_CACHE
        webView.addJavascriptInterface(Bridge(), "AndroidTcd")
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                checkConnection()
            }
            override fun onReceivedError(view: WebView?, request: Any?, error: Any?) {
                statusText.text = "Нет связи с сервером. Повтор через 5 сек…"
                statusText.postDelayed({ loadApp() }, 5000)   // автопереподключение
            }
        }

        findViewById<Button>(R.id.btn_save).setOnClickListener {
            serverUrl = urlInput.text.toString().trim().removeSuffix("/")
            getSharedPreferences("tcd", MODE_PRIVATE).edit().putString("server_url", serverUrl).apply()
            loadApp()
        }

        if (serverUrl.isBlank()) showSettings(true) else loadApp()
    }

    private fun showSettings(show: Boolean) {
        settingsPanel.visibility = if (show) View.VISIBLE else View.GONE
        webView.visibility = if (show) View.GONE else View.VISIBLE
    }

    private fun terminalUrl() = "$serverUrl/static/terminal.html"

    private fun loadApp() {
        if (serverUrl.isBlank()) { showSettings(true); return }
        showSettings(false)
        webView.loadUrl(terminalUrl())
    }

    private fun checkConnection() {
        statusText.text = "Сервер: $serverUrl"
    }

    /** Доставить код сканера в JS терминала. */
    private fun deliverScan(code: String) {
        feedback(true)
        val js = "window.onNativeScan ? window.onNativeScan(${jsonStr(code)}) : null;"
        webView.evaluateJavascript(js, null)
    }

    private fun jsonStr(s: String): String =
        "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

    /** Звук + вибрация. ok=true — успех, false — ошибка. */
    private fun feedback(ok: Boolean) {
        try {
            val tone = if (ok) ToneGenerator.STONE_OK else ToneGenerator.STONE_ERROR
            ToneGenerator(AudioManager.STREAM_MUSIC, 90).startTone(tone, 200)
        } catch (_: Exception) {}
        try {
            val v = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            if (Build.VERSION.SDK_INT >= 26) {
                v.vibrate(VibrationEffect.createOneShot(if (ok) 60 else 250,
                    VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION") v.vibrate(if (ok) 60 else 250)
            }
        } catch (_: Exception) {}
    }

    inner class Bridge {
        @JavascriptInterface
        fun baseUrl(): String = serverUrl

        @JavascriptInterface
        fun beepOk() { runOnUiThread { feedback(true) } }

        @JavascriptInterface
        fun beepError() { runOnUiThread { feedback(false) } }
    }

    // --- Перехват широковещательных рассылок сканера ---
    override fun onResume() {
        super.onResume()
        val filter = IntentFilter()
        scanActions.forEach { filter.addAction(it) }
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(scanReceiver, filter, Context.RECEIVER_EXPORTED)
        } else {
            registerReceiver(scanReceiver, filter)
        }
        handleIntent(intent)
    }

    override fun onPause() {
        super.onPause()
        try { unregisterReceiver(scanReceiver) } catch (_: Exception) {}
    }

    // Сканер может слать код через Intent на Activity
    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        extractCode(intent)?.let { deliverScan(it) }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }
}
