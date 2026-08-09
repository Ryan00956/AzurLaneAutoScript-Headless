package io.github.alasheadless.glescontract;

import android.app.Activity;
import android.opengl.GLES30;
import android.opengl.GLSurfaceView;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;

import java.nio.Buffer;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final String TAG = "ALAS_CONTRACT";
    private GLSurfaceView surfaceView;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        boolean expectNull = getIntent().getBooleanExtra("expect_null", false);
        surfaceView = new GLSurfaceView(this);
        surfaceView.setEGLContextClientVersion(3);
        surfaceView.setPreserveEGLContextOnPause(true);
        surfaceView.setRenderer(new ContractRenderer(expectNull));
        surfaceView.setRenderMode(GLSurfaceView.RENDERMODE_CONTINUOUSLY);
        setContentView(surfaceView);
    }

    @Override
    protected void onResume() {
        super.onResume();
        surfaceView.onResume();
    }

    @Override
    protected void onPause() {
        surfaceView.onPause();
        super.onPause();
    }

    private static final class ContractRenderer implements GLSurfaceView.Renderer {
        private static final float[] TRIANGLE = {
                0.0f, 0.6f,
                -0.6f, -0.6f,
                0.6f, -0.6f
        };

        private final boolean expectNull;
        private int program;
        private int width;
        private int height;
        private long frameCount;
        private long firstFrameNanos;
        private boolean contractRan;

        ContractRenderer(boolean expectNull) {
            this.expectNull = expectNull;
        }

        @Override
        public void onSurfaceCreated(javax.microedition.khronos.opengles.GL10 ignored,
                                     javax.microedition.khronos.egl.EGLConfig config) {
            firstFrameNanos = System.nanoTime();
            program = buildProgram(
                    "#version 300 es\nlayout(location=0) in vec2 p; void main(){gl_Position=vec4(p,0,1);}",
                    "#version 300 es\nprecision mediump float; out vec4 c; void main(){c=vec4(1,0,0,1);}");
            emit("surface-created", String.format(Locale.US,
                    "\"vendor\":%s,\"renderer\":%s,\"version\":%s,\"program\":%d",
                    quote(GLES30.glGetString(GLES30.GL_VENDOR)),
                    quote(GLES30.glGetString(GLES30.GL_RENDERER)),
                    quote(GLES30.glGetString(GLES30.GL_VERSION)),
                    program));
        }

        @Override
        public void onSurfaceChanged(javax.microedition.khronos.opengles.GL10 ignored,
                                     int newWidth, int newHeight) {
            width = newWidth;
            height = newHeight;
            GLES30.glViewport(0, 0, width, height);
            emit("surface-size", String.format(Locale.US,
                    "\"width\":%d,\"height\":%d", width, height));
        }

        @Override
        public void onDrawFrame(javax.microedition.khronos.opengles.GL10 ignored) {
            frameCount++;
            GLES30.glClearColor(0f, 0f, 0f, 1f);
            GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT);

            if (!contractRan && width > 0 && height > 0) {
                contractRan = true;
                runContract();
            }

            if (frameCount % 300 == 0) {
                double elapsedSeconds = (System.nanoTime() - firstFrameNanos) / 1_000_000_000.0;
                emit("heartbeat", String.format(Locale.US,
                        "\"frames\":%d,\"elapsed_seconds\":%.3f,\"fps\":%.3f",
                        frameCount, elapsedSeconds, frameCount / elapsedSeconds));
            }
        }

        private void runContract() {
            boolean passed = true;
            String failure = "";
            int[] ids = new int[1];

            GLES30.glGenBuffers(1, ids, 0);
            int vertexBuffer = ids[0];
            FloatBuffer vertices = ByteBuffer.allocateDirect(TRIANGLE.length * 4)
                    .order(ByteOrder.nativeOrder()).asFloatBuffer();
            vertices.put(TRIANGLE).position(0);
            GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, vertexBuffer);
            GLES30.glBufferData(GLES30.GL_ARRAY_BUFFER, TRIANGLE.length * 4, vertices,
                    GLES30.GL_STATIC_DRAW);

            GLES30.glGenTextures(1, ids, 0);
            int texture = ids[0];
            GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, texture);
            GLES30.glTexImage2D(GLES30.GL_TEXTURE_2D, 0, GLES30.GL_RGBA8,
                    4, 4, 0, GLES30.GL_RGBA, GLES30.GL_UNSIGNED_BYTE, null);

            GLES30.glGenFramebuffers(1, ids, 0);
            int framebuffer = ids[0];
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, framebuffer);
            GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER, GLES30.GL_COLOR_ATTACHMENT0,
                    GLES30.GL_TEXTURE_2D, texture, 0);
            int framebufferStatus = GLES30.glCheckFramebufferStatus(GLES30.GL_FRAMEBUFFER);

            GLES30.glViewport(0, 0, 4, 4);
            GLES30.glUseProgram(program);
            GLES30.glEnableVertexAttribArray(0);
            GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, vertexBuffer);
            GLES30.glVertexAttribPointer(0, 2, GLES30.GL_FLOAT, false, 0, 0);

            GLES30.glGenQueries(1, ids, 0);
            int query = ids[0];
            GLES30.glBeginQuery(GLES30.GL_ANY_SAMPLES_PASSED, query);
            GLES30.glDrawArrays(GLES30.GL_TRIANGLES, 0, 3);
            GLES30.glEndQuery(GLES30.GL_ANY_SAMPLES_PASSED);

            long sync = GLES30.glFenceSync(GLES30.GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
            int waitResult = GLES30.glClientWaitSync(sync, GLES30.GL_SYNC_FLUSH_COMMANDS_BIT,
                    1_000_000_000L);

            int[] queryResult = new int[1];
            GLES30.glGetQueryObjectuiv(query, GLES30.GL_QUERY_RESULT, queryResult, 0);

            ByteBuffer directReadback = ByteBuffer.allocateDirect(4);
            GLES30.glReadPixels(0, 0, 1, 1, GLES30.GL_RGBA, GLES30.GL_UNSIGNED_BYTE,
                    directReadback);
            String directHex = hex(directReadback, 4);

            GLES30.glGenBuffers(1, ids, 0);
            int pixelPackBuffer = ids[0];
            GLES30.glBindBuffer(GLES30.GL_PIXEL_PACK_BUFFER, pixelPackBuffer);
            GLES30.glBufferData(GLES30.GL_PIXEL_PACK_BUFFER, 4, null, GLES30.GL_STREAM_READ);
            GLES30.glReadPixels(0, 0, 1, 1, GLES30.GL_RGBA, GLES30.GL_UNSIGNED_BYTE, 0);
            Buffer mapped = GLES30.glMapBufferRange(GLES30.GL_PIXEL_PACK_BUFFER, 0, 4,
                    GLES30.GL_MAP_READ_BIT);
            String pboHex = mapped instanceof ByteBuffer ? hex((ByteBuffer) mapped, 4) : "unmapped";
            boolean unmapResult = GLES30.glUnmapBuffer(GLES30.GL_PIXEL_PACK_BUFFER);

            int error = GLES30.glGetError();
            String renderer = GLES30.glGetString(GLES30.GL_RENDERER);
            boolean rendererIsNull = renderer != null && renderer.toUpperCase(Locale.ROOT).contains("NULL");
            boolean readbackIsZero = "00000000".equals(directHex) && "00000000".equals(pboHex);

            if (program == 0) {
                passed = false;
                failure = "program-link";
            } else if (framebufferStatus != GLES30.GL_FRAMEBUFFER_COMPLETE) {
                passed = false;
                failure = "framebuffer-incomplete";
            } else if (sync == 0L || waitResult == GLES30.GL_WAIT_FAILED) {
                passed = false;
                failure = "sync-failed";
            } else if (query == 0) {
                passed = false;
                failure = "query-create";
            } else if (!unmapResult) {
                passed = false;
                failure = "pbo-unmap";
            } else if (error != GLES30.GL_NO_ERROR) {
                passed = false;
                failure = "gl-error-0x" + Integer.toHexString(error);
            } else if (expectNull && !rendererIsNull) {
                passed = false;
                failure = "renderer-not-null";
            } else if (expectNull && !readbackIsZero) {
                passed = false;
                failure = "readback-not-zero";
            }

            emit("contract-result", String.format(Locale.US,
                    "\"passed\":%s,\"failure\":%s,\"expect_null\":%s," +
                            "\"renderer_is_null\":%s,\"surface_width\":%d," +
                            "\"surface_height\":%d,\"framebuffer_status\":%d," +
                            "\"wait_result\":%d,\"direct_rgba\":%s,\"pbo_rgba\":%s," +
                            "\"vertex_buffer\":%d,\"texture\":%d,\"framebuffer\":%d," +
                            "\"pixel_pack_buffer\":%d,\"query\":%d," +
                            "\"query_result\":%d,\"gl_error\":%d",
                    passed, quote(failure), expectNull, rendererIsNull, width, height,
                    framebufferStatus, waitResult, quote(directHex), quote(pboHex),
                    vertexBuffer, texture, framebuffer, pixelPackBuffer, query,
                    queryResult[0], error));

            if (sync != 0L) GLES30.glDeleteSync(sync);
            if (query != 0) GLES30.glDeleteQueries(1, new int[]{query}, 0);
            GLES30.glDeleteBuffers(1, new int[]{pixelPackBuffer}, 0);
            GLES30.glDeleteFramebuffers(1, new int[]{framebuffer}, 0);
            GLES30.glDeleteTextures(1, new int[]{texture}, 0);
            GLES30.glDeleteBuffers(1, new int[]{vertexBuffer}, 0);
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0);
            GLES30.glViewport(0, 0, width, height);
        }

        private static int buildProgram(String vertexSource, String fragmentSource) {
            int vertex = compile(GLES30.GL_VERTEX_SHADER, vertexSource);
            int fragment = compile(GLES30.GL_FRAGMENT_SHADER, fragmentSource);
            if (vertex == 0 || fragment == 0) return 0;
            int linkedProgram = GLES30.glCreateProgram();
            GLES30.glAttachShader(linkedProgram, vertex);
            GLES30.glAttachShader(linkedProgram, fragment);
            GLES30.glLinkProgram(linkedProgram);
            int[] status = new int[1];
            GLES30.glGetProgramiv(linkedProgram, GLES30.GL_LINK_STATUS, status, 0);
            GLES30.glDeleteShader(vertex);
            GLES30.glDeleteShader(fragment);
            if (status[0] == 0) {
                emit("program-link-error", "\"log\":" + quote(GLES30.glGetProgramInfoLog(linkedProgram)));
                GLES30.glDeleteProgram(linkedProgram);
                return 0;
            }
            return linkedProgram;
        }

        private static int compile(int type, String source) {
            int shader = GLES30.glCreateShader(type);
            GLES30.glShaderSource(shader, source);
            GLES30.glCompileShader(shader);
            int[] status = new int[1];
            GLES30.glGetShaderiv(shader, GLES30.GL_COMPILE_STATUS, status, 0);
            if (status[0] == 0) {
                emit("shader-compile-error", "\"log\":" + quote(GLES30.glGetShaderInfoLog(shader)));
                GLES30.glDeleteShader(shader);
                return 0;
            }
            return shader;
        }

        private static String hex(ByteBuffer data, int count) {
            ByteBuffer copy = data.duplicate();
            copy.position(0);
            StringBuilder value = new StringBuilder(count * 2);
            for (int i = 0; i < count && copy.hasRemaining(); i++) {
                value.append(String.format(Locale.US, "%02x", copy.get() & 0xff));
            }
            return value.toString();
        }

        private static String quote(String value) {
            if (value == null) return "null";
            return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
        }

        private static void emit(String event, String fields) {
            Log.i(TAG, "{\"event\":" + quote(event) + ",\"elapsed_ms\":" +
                    SystemClock.elapsedRealtime() + "," + fields + "}");
        }
    }
}
