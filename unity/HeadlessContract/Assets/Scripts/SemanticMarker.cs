using UnityEngine;

namespace Alas.Headless.Contract
{
    public sealed class SemanticMarker : MonoBehaviour
    {
        [SerializeField] private string semanticId = "unset";
        [SerializeField] private int generation;

        public string SemanticId => semanticId;
        public int Generation => generation;

        public void Initialize(string id)
        {
            semanticId = id;
            generation++;
        }
    }
}
