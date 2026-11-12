using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace ReleaseDesk.Editor
{
    /// <summary>One shot from Store/shots.json. <see cref="setup"/> is game-defined (for example Flecs Script).</summary>
    [Serializable]
    public class ShotRequest
    {
        public string name = "";
        public string[] stores = { "steam" };
        public int width = 1920;
        public int height = 1080;
        public float wait = 2f;
        public string setup = "";
    }

    /// <summary>
    /// The game's side of screenshot capture. Release Desk stays engine-agnostic: the game implements this once
    /// (for example by running the shot's Flecs Script) and returns the camera to render.
    /// </summary>
    public interface IShotStage
    {
        /// <summary>Called in Play mode before each shot. Return the camera to render, or null for Camera.main.</summary>
        Task<Camera> Prepare(ShotRequest shot);

        /// <summary>Called once after the last shot, still in Play mode.</summary>
        void Finish();
    }

    /// <summary>
    /// Enters Play mode, prepares each shot through the game's <see cref="IShotStage"/>, renders the camera into an
    /// image of the exact requested size and writes Store/shots/&lt;store&gt;/&lt;name&gt;.png. The result is written as
    /// JSON because the capture outlives the CLI call that starts it.
    /// </summary>
    [InitializeOnLoad]
    public static class ShotCapture
    {
        private const string PendingKey = "ReleaseDesk.ShotCapture.Pending";

        [Serializable]
        private class ShotList
        {
            public ShotRequest[] shots = Array.Empty<ShotRequest>();
        }

        [Serializable]
        private class Pending
        {
            public string shotsPath = "";
            public string outputRoot = "";
            public string resultPath = "";
            public string only = "";
            public bool exitAfter;
        }

        [Serializable]
        private class Result
        {
            public string result = "";
            public string finished = "";
            public double seconds;
            public List<string> files = new List<string>();
            public List<string> errors = new List<string>();
        }

        static ShotCapture()
        {
            EditorApplication.playModeStateChanged += OnPlayModeChanged;
            // Domain reload on entering Play mode: resume from the saved request.
            if (EditorApplication.isPlaying && !string.IsNullOrEmpty(SessionState.GetString(PendingKey, "")))
                EditorApplication.delayCall += Run;
        }

        /// <summary>Starts capturing. only: a shot name to capture alone, or empty for all.</summary>
        public static string Start(string shotsPath, string outputRoot, string resultPath, string only = "")
        {
            if (!File.Exists(shotsPath))
                throw new FileNotFoundException("No shot list.", shotsPath);
            if (StageType() == null)
                throw new InvalidOperationException("The game has no IShotStage implementation.");
            if (File.Exists(resultPath))
                File.Delete(resultPath);
            var pending = new Pending { shotsPath = shotsPath, outputRoot = outputRoot, resultPath = resultPath, only = only ?? "", exitAfter = !EditorApplication.isPlaying };
            SessionState.SetString(PendingKey, JsonUtility.ToJson(pending));
            if (EditorApplication.isPlaying)
                EditorApplication.delayCall += Run;
            else
                EditorApplication.EnterPlaymode();
            return "Capture started";
        }

        private static void OnPlayModeChanged(PlayModeStateChange change)
        {
            if (change == PlayModeStateChange.EnteredPlayMode && !string.IsNullOrEmpty(SessionState.GetString(PendingKey, "")))
                EditorApplication.delayCall += Run;
        }

        private static Type StageType() =>
            TypeCache.GetTypesDerivedFrom<IShotStage>().FirstOrDefault(t => !t.IsAbstract && !t.IsInterface);

        private static bool running;

        private static async void Run()
        {
            if (running)
                return;
            string json = SessionState.GetString(PendingKey, "");
            if (string.IsNullOrEmpty(json))
                return;
            running = true;
            SessionState.EraseString(PendingKey);
            var pending = JsonUtility.FromJson<Pending>(json);
            var result = new Result();
            var started = DateTime.Now;
            IShotStage stage = null;
            try
            {
                var list = JsonUtility.FromJson<ShotList>(File.ReadAllText(pending.shotsPath));
                var shots = list.shots.Where(s => string.IsNullOrEmpty(pending.only) || s.name == pending.only).ToArray();
                stage = (IShotStage)Activator.CreateInstance(StageType());
                await Task.Delay(1500); // let startup settle
                foreach (var shot in shots)
                {
                    try
                    {
                        var camera = await stage.Prepare(shot) ?? Camera.main;
                        if (camera == null)
                            throw new InvalidOperationException("No camera to render.");
                        await Task.Delay(Mathf.RoundToInt(Mathf.Max(0, shot.wait) * 1000));
                        byte[] png = Render(camera, shot.width, shot.height);
                        foreach (string store in shot.stores)
                        {
                            string path = Path.Combine(pending.outputRoot, store, shot.name + ".png");
                            Directory.CreateDirectory(Path.GetDirectoryName(path));
                            File.WriteAllBytes(path, png);
                            result.files.Add(path);
                        }
                    }
                    catch (Exception error)
                    {
                        result.errors.Add($"{shot.name}: {error.Message}");
                    }
                }
                stage.Finish();
                result.result = result.errors.Count == 0 ? "Succeeded" : result.files.Count > 0 ? "Partial" : "Failed";
            }
            catch (Exception error)
            {
                result.result = "Failed";
                result.errors.Add(error.Message);
            }
            finally
            {
                result.finished = DateTime.Now.ToString("yyyy-MM-dd HH:mm");
                result.seconds = Math.Round((DateTime.Now - started).TotalSeconds, 1);
                Directory.CreateDirectory(Path.GetDirectoryName(pending.resultPath) ?? ".");
                File.WriteAllText(pending.resultPath, JsonUtility.ToJson(result, true));
                running = false;
                if (pending.exitAfter)
                    EditorApplication.ExitPlaymode();
            }
        }

        /// <summary>Renders the camera off-screen at an exact size, independent of the Game view.</summary>
        private static byte[] Render(Camera camera, int width, int height)
        {
            var target = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);
            var previousTarget = camera.targetTexture;
            var previousActive = RenderTexture.active;
            try
            {
                var request = new UnityEngine.Rendering.RenderPipeline.StandardRequest { destination = target };
                if (UnityEngine.Rendering.RenderPipeline.SupportsRenderRequest(camera, request))
                    UnityEngine.Rendering.RenderPipeline.SubmitRenderRequest(camera, request);
                else
                {
                    camera.targetTexture = target;
                    camera.Render();
                }
                RenderTexture.active = target;
                var image = new Texture2D(width, height, TextureFormat.RGB24, false);
                image.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                image.Apply();
                byte[] png = image.EncodeToPNG();
                UnityEngine.Object.DestroyImmediate(image);
                return png;
            }
            finally
            {
                camera.targetTexture = previousTarget;
                RenderTexture.active = previousActive;
                RenderTexture.ReleaseTemporary(target);
            }
        }
    }
}
