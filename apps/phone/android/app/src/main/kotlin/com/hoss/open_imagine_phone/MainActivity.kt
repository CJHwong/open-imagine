package com.hoss.open_imagine_phone

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import java.io.IOException
import java.util.concurrent.Executors
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private lateinit var studioInputs: StudioInputs
    private external fun nativeInit(context: Context)
    // A saved clip can be hundreds of megabytes. Writing it on the platform thread stalls
    // every animation and lifecycle callback for the length of the write.
    private val writer = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // iroh resolves names through Android's APIs. A standalone process has no
        // Java VM, so the pipe runs inside this app and receives both here.
        nativeInit(applicationContext)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        studioInputs = StudioInputs(this,
            MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "open_imagine/inputs"))
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "open_imagine/native")
            .setMethodCallHandler { call, result ->
                if (call.method == "nativeLibraryDir") {
                    result.success(applicationInfo.nativeLibraryDir)
                } else {
                    result.notImplemented()
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "open_imagine/files")
            .setMethodCallHandler { call, result ->
                if (call.method == "save") {
                    val name = call.argument<String>("name") ?: "download"
                    val mime = call.argument<String>("mime") ?: "application/octet-stream"
                    val bytes = call.argument<ByteArray>("bytes") ?: ByteArray(0)
                    writer.execute {
                        try {
                            result.success(saveFile(name, mime, bytes))
                        } catch (error: Exception) {
                            result.error("save-failed", error.message ?: "the file was not saved", null)
                        }
                    }
                } else {
                    result.notImplemented()
                }
            }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        studioInputs.onRequestPermissionsResult(requestCode, grantResults)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, intent: Intent?) {
        super.onActivityResult(requestCode, resultCode, intent)
        studioInputs.onActivityResult(requestCode, resultCode, intent)
    }

    override fun onDestroy() {
        studioInputs.dispose()
        writer.shutdown()
        super.onDestroy()
    }

    private fun safeName(name: String): String {
        // Only a leaf: a name carrying separators or `..` used to point the old path at
        // another file this app can write.
        val leaf = name.substringAfterLast('/').substringAfterLast('\\').trim()
        if (leaf.isEmpty() || leaf == "." || leaf == ".." || leaf.any { it.code < 0x20 }) {
            return "download"
        }
        return leaf
    }

    private fun requireSpace(bytes: ByteArray) {
        // A clip can be hundreds of megabytes. A write that runs out of space fails halfway
        // and leaves a pending row to clean up, so the room is checked before it starts.
        val directory = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: filesDir
        val free = directory.usableSpace
        if (free in 1 until bytes.size.toLong() + SPACE_MARGIN_BYTES) {
            throw IOException("Not enough free storage to save this file. ${bytes.size} bytes are needed.")
        }
    }

    private fun saveFile(name: String, mime: String, bytes: ByteArray): String {
        requireSpace(bytes)
        val leaf = safeName(name)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, leaf)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IllegalStateException("No Downloads collection")
            try {
                val stream = contentResolver.openOutputStream(uri)
                    ?: throw IOException("Android opened no stream for the download")
                stream.use { it.write(bytes) }
                val written = contentResolver.openFileDescriptor(uri, "r")?.use { it.statSize } ?: -1
                if (written != bytes.size.toLong()) {
                    throw IOException("The download was not written whole")
                }
            } catch (error: Exception) {
                // A pending row with nothing in it is invisible to the person and stays
                // for ever. It goes with the failure.
                contentResolver.delete(uri, null, null)
                throw error
            }
            val done = ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }
            contentResolver.update(uri, done, null, null)
            return uri.toString()
        }
        val folder = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: filesDir
        folder.mkdirs()
        val file = File(folder, leaf)
        // `toPath` needs API 26 and this app runs on 24. The canonical path with its
        // separator is the same test and works there.
        val root = folder.canonicalFile
        val target = file.canonicalFile
        if (target != root && !target.path.startsWith(root.path + File.separator)) {
            throw IOException("The download name points outside the downloads folder")
        }
        file.writeBytes(bytes)
        return file.absolutePath
    }

    companion object {
        // What the filesystem needs beyond the file itself: allocation blocks and the
        // directory entry, with room to spare.
        private const val SPACE_MARGIN_BYTES = 8L * 1024 * 1024

        init {
            System.loadLibrary("openimagine_pipe")
        }
    }
}
