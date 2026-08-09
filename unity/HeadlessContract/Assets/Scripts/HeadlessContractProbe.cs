using System;
using System.Collections;
using System.IO;
using System.Text;
using Unity.Collections;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Alas.Headless.Contract
{
    public sealed class HeadlessContractProbe : MonoBehaviour
    {
        private const string LogPrefix = "ALAS_UNITY_CONTRACT ";
        private RectTransform animatedRect;
        private Text statusText;
        private SemanticMarker buttonMarker;
        private int updateCount;
        private int fixedUpdateCount;
        private int endOfFrameCount;
        private int asyncReadbackCompleted;
        private int asyncReadbackErrors;
        private bool asyncReadbackPending;
        private bool asyncReadbackTimeoutReported;
        private float asyncReadbackStartedAt;
        private float startedAt;
        private string telemetryPath;
        private int sceneGeneration = 1;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            if (FindObjectOfType<HeadlessContractProbe>() != null) return;
            var host = new GameObject("ALAS.HeadlessContractProbe");
            DontDestroyOnLoad(host);
            host.AddComponent<HeadlessContractProbe>();
        }

        private void Awake()
        {
            startedAt = Time.realtimeSinceStartup;
            telemetryPath = Path.Combine(Application.persistentDataPath, "alas-unity-contract.jsonl");
            BuildUi();
            EmitUnityThread();
            StartCoroutine(EndOfFrameLoop());
            StartCoroutine(SceneTransitionLoop());
            StartCoroutine(RenderTextureLoop());
            Emit("startup", "\"unity\":" + Quote(Application.unityVersion) +
                ",\"graphics_device\":" + Quote(SystemInfo.graphicsDeviceName) +
                ",\"graphics_type\":" + Quote(SystemInfo.graphicsDeviceType.ToString()) +
                ",\"screen_width\":" + Screen.width +
                ",\"screen_height\":" + Screen.height);
        }

        private void Update()
        {
            updateCount++;
            if (animatedRect != null)
            {
                animatedRect.anchoredPosition = new Vector2(
                    Mathf.Sin(Time.realtimeSinceStartup) * 120f,
                    Mathf.Cos(Time.realtimeSinceStartup * 0.5f) * 30f);
            }

            if (asyncReadbackPending && !asyncReadbackTimeoutReported &&
                Time.realtimeSinceStartup - asyncReadbackStartedAt > 10f)
            {
                asyncReadbackTimeoutReported = true;
                Emit("async-readback-timeout", "\"timeout_seconds\":10");
            }

            if (updateCount % 300 == 0)
            {
                string state = "updates=" + updateCount + " fixed=" + fixedUpdateCount +
                               " eof=" + endOfFrameCount + " readback=" + asyncReadbackCompleted +
                               " readback_errors=" + asyncReadbackErrors;
                if (statusText != null) statusText.text = state;
                Emit("heartbeat", "\"updates\":" + updateCount +
                    ",\"fixed_updates\":" + fixedUpdateCount +
                    ",\"end_of_frame\":" + endOfFrameCount +
                    ",\"readback_completed\":" + asyncReadbackCompleted +
                    ",\"readback_errors\":" + asyncReadbackErrors +
                    ",\"panel_x\":" + animatedRect.anchoredPosition.x.ToString("F3",
                        System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"panel_y\":" + animatedRect.anchoredPosition.y.ToString("F3",
                        System.Globalization.CultureInfo.InvariantCulture) +
                    ",\"button_semantic\":" + Quote(buttonMarker.SemanticId) +
                    ",\"button_generation\":" + buttonMarker.Generation +
                    ",\"uptime\":" + (Time.realtimeSinceStartup - startedAt).ToString("F3",
                        System.Globalization.CultureInfo.InvariantCulture));
            }
        }

        private void FixedUpdate()
        {
            fixedUpdateCount++;
        }

        private void OnApplicationPause(bool paused)
        {
            Emit("application-pause", "\"paused\":" + (paused ? "true" : "false"));
        }

        private void BuildUi()
        {
            if (FindObjectOfType<EventSystem>() == null)
            {
                var eventSystem = new GameObject("EventSystem");
                eventSystem.AddComponent<EventSystem>();
                eventSystem.AddComponent<StandaloneInputModule>();
                DontDestroyOnLoad(eventSystem);
            }

            var canvasObject = new GameObject("ContractCanvas");
            DontDestroyOnLoad(canvasObject);
            var canvas = canvasObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvasObject.AddComponent<CanvasScaler>().uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            canvasObject.GetComponent<CanvasScaler>().referenceResolution = new Vector2(1280, 720);
            canvasObject.AddComponent<GraphicRaycaster>();
            canvasObject.AddComponent<SemanticMarker>().Initialize("contract/root");

            var panel = new GameObject("AnimatedPanel");
            panel.transform.SetParent(canvasObject.transform, false);
            animatedRect = panel.AddComponent<RectTransform>();
            animatedRect.sizeDelta = new Vector2(520, 180);
            panel.AddComponent<Image>().color = new Color(0.05f, 0.15f, 0.2f, 0.9f);
            panel.AddComponent<SemanticMarker>().Initialize("contract/animated-panel");

            var textObject = new GameObject("StatusText");
            textObject.transform.SetParent(panel.transform, false);
            statusText = textObject.AddComponent<Text>();
            statusText.font = Resources.GetBuiltinResource<Font>("Arial.ttf");
            statusText.alignment = TextAnchor.MiddleCenter;
            statusText.color = Color.white;
            statusText.text = "ALAS headless Unity contract";
            var textRect = statusText.rectTransform;
            textRect.anchorMin = Vector2.zero;
            textRect.anchorMax = Vector2.one;
            textRect.offsetMin = Vector2.zero;
            textRect.offsetMax = Vector2.zero;

            var buttonObject = new GameObject("ContractButton");
            buttonObject.transform.SetParent(canvasObject.transform, false);
            var buttonRect = buttonObject.AddComponent<RectTransform>();
            buttonRect.sizeDelta = new Vector2(280, 90);
            buttonRect.anchoredPosition = new Vector2(0, -220);
            buttonObject.AddComponent<Image>().color = new Color(0.1f, 0.65f, 0.45f, 1f);
            var button = buttonObject.AddComponent<Button>();
            buttonMarker = buttonObject.AddComponent<SemanticMarker>();
            buttonMarker.Initialize("contract/button");
            button.onClick.AddListener(() =>
            {
                buttonMarker.Initialize("contract/button-clicked");
                button.interactable = false;
                Emit("button-click", "\"generation\":" + buttonMarker.Generation);
            });
        }

        private IEnumerator EndOfFrameLoop()
        {
            while (true)
            {
                yield return new WaitForEndOfFrame();
                endOfFrameCount++;
            }
        }

        private IEnumerator SceneTransitionLoop()
        {
            Scene previousScene = SceneManager.GetActiveScene();
            while (true)
            {
                yield return new WaitForSecondsRealtime(15f);
                sceneGeneration++;
                var scene = SceneManager.CreateScene("ContractScene-" + sceneGeneration);
                var markerObject = new GameObject("SceneMarker-" + sceneGeneration);
                markerObject.AddComponent<SemanticMarker>().Initialize("contract/scene/" + sceneGeneration);
                SceneManager.MoveGameObjectToScene(markerObject, scene);
                SceneManager.SetActiveScene(scene);
                Emit("scene-transition", "\"scene\":" + Quote(scene.name) +
                    ",\"generation\":" + sceneGeneration);
                if (previousScene.IsValid() && previousScene.isLoaded)
                {
                    SceneManager.UnloadSceneAsync(previousScene);
                }
                previousScene = scene;
            }
        }

        private void EmitUnityThread()
        {
            using (var process = new AndroidJavaClass("android.os.Process"))
            {
                Emit("unity-thread", "\"tid\":" + process.CallStatic<int>("myTid"));
            }
        }

        private IEnumerator RenderTextureLoop()
        {
            while (true)
            {
                yield return new WaitForSecondsRealtime(5f);
                if (asyncReadbackPending)
                {
                    Emit("async-readback-pending", "\"age_seconds\":" +
                        (Time.realtimeSinceStartup - asyncReadbackStartedAt).ToString("F3",
                            System.Globalization.CultureInfo.InvariantCulture));
                    continue;
                }
                var texture = new RenderTexture(16, 16, 0, RenderTextureFormat.ARGB32);
                texture.Create();
                if (SystemInfo.supportsAsyncGPUReadback)
                {
                    asyncReadbackPending = true;
                    asyncReadbackTimeoutReported = false;
                    asyncReadbackStartedAt = Time.realtimeSinceStartup;
                    AsyncGPUReadback.Request(texture, 0, TextureFormat.RGBA32, request =>
                    {
                        asyncReadbackPending = false;
                        if (request.hasError)
                        {
                            asyncReadbackErrors++;
                            Emit("async-readback-error", "\"errors\":" + asyncReadbackErrors);
                        }
                        else
                        {
                            NativeArray<byte> data = request.GetData<byte>();
                            asyncReadbackCompleted++;
                            Emit("async-readback", "\"bytes\":" + data.Length +
                                ",\"first\":" + (data.Length > 0 ? data[0] : 0));
                        }
                        texture.Release();
                        Destroy(texture);
                    });
                }
                else
                {
                    Emit("async-readback-unsupported", "\"supported\":false");
                    texture.Release();
                    Destroy(texture);
                }
            }
        }

        private void Emit(string eventName, string fields)
        {
            string line = "{\"event\":" + Quote(eventName) +
                          ",\"realtime\":" + Time.realtimeSinceStartup.ToString("F3",
                              System.Globalization.CultureInfo.InvariantCulture) +
                          "," + fields + "}";
            Debug.Log(LogPrefix + line);
            try
            {
                File.AppendAllText(telemetryPath, line + Environment.NewLine, Encoding.UTF8);
            }
            catch (Exception exception)
            {
                Debug.LogError(LogPrefix + "telemetry-write-failed " + exception.Message);
            }
        }

        private static string Quote(string value)
        {
            if (value == null) return "null";
            return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
        }
    }
}
