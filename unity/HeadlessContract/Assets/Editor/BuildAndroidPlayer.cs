using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Alas.Headless.Contract.Editor
{
    public static class BuildAndroidPlayer
    {
        private const string ScenePath = "Assets/Scenes/ContractBootstrap.unity";
        private const string OutputPath = "Build/HeadlessContract.apk";

        public static void Build()
        {
            if (Application.unityVersion != "2022.3.62f3")
            {
                throw new InvalidOperationException(
                    "This contract must be built with Unity 2022.3.62f3; found " +
                    Application.unityVersion + ".");
            }

            EnsureBootstrapScene();
            ConfigurePlayer();

            Directory.CreateDirectory(Path.GetDirectoryName(OutputPath) ?? "Build");
            var options = new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = OutputPath,
                target = BuildTarget.Android,
                options = BuildOptions.Development
            };
            BuildReport report = BuildPipeline.BuildPlayer(options);
            if (report.summary.result != BuildResult.Succeeded)
            {
                throw new InvalidOperationException(
                    "Android contract build failed: " + report.summary.result +
                    " errors=" + report.summary.totalErrors);
            }

            Debug.Log("ALAS_UNITY_BUILD " + JsonUtility.ToJson(new BuildEvidence
            {
                unity = Application.unityVersion,
                output = Path.GetFullPath(OutputPath),
                bytes = report.summary.totalSize,
                durationSeconds = report.summary.totalTime.TotalSeconds
            }));
        }

        private static void EnsureBootstrapScene()
        {
            Directory.CreateDirectory("Assets/Scenes");
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var marker = new GameObject("ContractBootstrapMarker");
            marker.AddComponent<SemanticMarker>().Initialize("contract/bootstrap");
            if (!EditorSceneManager.SaveScene(scene, ScenePath))
            {
                throw new InvalidOperationException("Unable to save " + ScenePath);
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
        }

        private static void ConfigurePlayer()
        {
            if (!EditorUserBuildSettings.SwitchActiveBuildTarget(
                    BuildTargetGroup.Android, BuildTarget.Android))
            {
                throw new InvalidOperationException("Unable to switch the active target to Android.");
            }

            PlayerSettings.companyName = "ALAS Headless Research";
            PlayerSettings.productName = "ALAS Headless Contract";
            PlayerSettings.bundleVersion = "0.1.0";
            PlayerSettings.SetApplicationIdentifier(
                BuildTargetGroup.Android, "io.github.alasheadless.unitycontract");
            PlayerSettings.SetScriptingBackend(
                BuildTargetGroup.Android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.X86_64;
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel29;
            PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevelAuto;
            PlayerSettings.Android.bundleVersionCode = 1;
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.LandscapeLeft;
            EditorUserBuildSettings.buildAppBundle = false;
        }

        [Serializable]
        private sealed class BuildEvidence
        {
            public string unity;
            public string output;
            public ulong bytes;
            public double durationSeconds;
        }
    }
}
