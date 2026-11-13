package com.hoss.open_imagine_phone

import android.Manifest
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Base64
import android.webkit.MimeTypeMap
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.IOException
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.util.concurrent.Executors

class StudioInputs(private val activity: Activity, private val channel: MethodChannel) {
    private val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    private val reader = Executors.newSingleThreadExecutor()
    private var microphoneResult: MethodChannel.Result? = null
    private var pickerResult: MethodChannel.Result? = null
    private var clipboardRevision = 0L
    private val clipboardListener = ClipboardManager.OnPrimaryClipChangedListener {
        clipboardRevision++
        if (activity.hasWindowFocus()) channel.invokeMethod("clipboardChanged", null)
    }

    init {
        clipboard.addPrimaryClipChangedListener(clipboardListener)
        channel.setMethodCallHandler(::handle)
    }

    private fun handle(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "microphone" -> requestMicrophone(result)
            "pickFiles" -> pickFiles(call, result)
            "clipboardDescribe" -> result.success(describeClipboard())
            "clipboardRead" -> readClipboard(result)
            else -> result.notImplemented()
        }
    }

    private fun requestMicrophone(result: MethodChannel.Result) {
        if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            result.success(true)
            return
        }
        if (microphoneResult != null) {
            result.success(false)
            return
        }
        microphoneResult = result
        activity.requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), MICROPHONE_REQUEST)
    }

    fun onRequestPermissionsResult(requestCode: Int, grantResults: IntArray) {
        if (requestCode != MICROPHONE_REQUEST) return
        microphoneResult?.success(grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED)
        microphoneResult = null
    }

    private fun mimeTypes(acceptTypes: List<String>): List<String> {
        return acceptTypes.mapNotNull { accepted ->
            if (accepted.startsWith(".")) {
                MimeTypeMap.getSingleton().getMimeTypeFromExtension(accepted.drop(1).lowercase())
            } else {
                accepted.takeIf { it.contains('/') }
            }
        }.distinct()
    }

    private fun pickFiles(call: MethodCall, result: MethodChannel.Result) {
        if (pickerResult != null) {
            result.error("picker_busy", "A file selector is already open.", null)
            return
        }
        val accepted = mimeTypes(call.argument<List<String>>("acceptTypes") ?: emptyList())
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = accepted.singleOrNull() ?: "*/*"
            if (accepted.size > 1) putExtra(Intent.EXTRA_MIME_TYPES, accepted.toTypedArray())
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, call.argument<Boolean>("multiple") ?: false)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        pickerResult = result
        try {
            activity.startActivityForResult(intent, FILE_REQUEST)
        } catch (error: ActivityNotFoundException) {
            pickerResult = null
            result.error("picker_unavailable", "Android has no file selector.", null)
        }
    }

    fun onActivityResult(requestCode: Int, resultCode: Int, intent: Intent?) {
        if (requestCode != FILE_REQUEST) return
        val selected = if (resultCode == Activity.RESULT_OK) selectedUris(intent) else emptyList()
        pickerResult?.success(selected)
        pickerResult = null
    }

    private fun selectedUris(intent: Intent?): List<String> {
        val clips = intent?.clipData
        if (clips != null) return (0 until clips.itemCount).map { clips.getItemAt(it).uri.toString() }
        return intent?.data?.let { listOf(it.toString()) } ?: emptyList()
    }

    private fun describeClipboard(): Map<String, Any> {
        if (!activity.hasWindowFocus()) return mapOf("types" to emptyList<String>(), "token" to "")
        val description = clipboard.primaryClipDescription
            ?: return mapOf("types" to emptyList<String>(), "token" to "")
        val timestamp = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) description.timestamp else 0L
        val types = (0 until description.mimeTypeCount).map { description.getMimeType(it) }
        return mapOf("types" to types, "token" to "$timestamp:$clipboardRevision")
    }

    private fun readClipboard(result: MethodChannel.Result) {
        if (!activity.hasWindowFocus()) {
            result.error("clipboard_unavailable", "Return to the app before pasting.", null)
            return
        }
        // Content access follows the Paste action. Detection reads only the description.
        val clip = clipboard.primaryClip
        val uri = if (clip != null && clip.itemCount > 0) clip.getItemAt(0).uri else null
        if (uri == null || uri.scheme != "content") {
            result.success(emptyList<Any>())
            return
        }
        reader.execute {
            try {
                val file = clipboardFile(uri)
                activity.runOnUiThread { result.success(file?.let { listOf(it) } ?: emptyList<Any>()) }
            } catch (error: IOException) {
                activity.runOnUiThread { result.error("clipboard_unreadable", "Cannot read the copied file.", null) }
            } catch (error: SecurityException) {
                activity.runOnUiThread { result.error("clipboard_denied", "Android denies access to the copied file.", null) }
            }
        }
    }

    private fun clipboardFile(uri: android.net.Uri): Map<String, String>? {
        val resolver = activity.contentResolver
        val mime = resolver.getType(uri) ?: return null
        if (!mime.startsWith("image/") && !mime.startsWith("audio/") && !mime.startsWith("video/")) return null
        val bytes = resolver.openInputStream(uri)?.use { readBounded(it) }
            ?: throw IOException("No clipboard stream")
        if (bytes.size > MAX_CLIPBOARD_BYTES) throw IOException("The copied file exceeds 32 MB")
        val extension = MimeTypeMap.getSingleton().getExtensionFromMimeType(mime) ?: "bin"
        return mapOf("name" to "clipboard.$extension", "mime" to mime,
            "base64" to Base64.encodeToString(bytes, Base64.NO_WRAP))
    }

    private fun readBounded(input: InputStream): ByteArray {
        val bytes = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        var count = input.read(buffer)
        while (count != -1) {
            if (bytes.size() + count > MAX_CLIPBOARD_BYTES) throw IOException("The copied file exceeds 32 MB")
            bytes.write(buffer, 0, count)
            count = input.read(buffer)
        }
        return bytes.toByteArray()
    }

    fun dispose() {
        clipboard.removePrimaryClipChangedListener(clipboardListener)
        channel.setMethodCallHandler(null)
        reader.shutdown()
        microphoneResult?.success(false)
        pickerResult?.success(emptyList<String>())
        microphoneResult = null
        pickerResult = null
    }

    companion object {
        private const val MICROPHONE_REQUEST = 8701
        private const val FILE_REQUEST = 8702
        private const val MAX_CLIPBOARD_BYTES = 32 * 1024 * 1024
    }
}
