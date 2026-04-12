using UnityEngine;
using UnityEngine.EventSystems;

public class HoverScale : MonoBehaviour, IPointerEnterHandler, IPointerExitHandler
{
    private Vector3 originalScale;
    private Vector3 targetScale;

    public float scaleFactor = 0.9f; // nhỏ lại 90%
    public float speed = 10f;

    void Awake()
    {
        // Lưu scale gốc sớm để tránh lỗi
        originalScale = transform.localScale;
        targetScale = originalScale;
    }

    void Update()
    {
        transform.localScale = Vector3.Lerp(transform.localScale, targetScale, Time.deltaTime * speed);
    }

    public void OnPointerEnter(PointerEventData eventData)
    {
        targetScale = originalScale * scaleFactor;
    }

    public void OnPointerExit(PointerEventData eventData)
    {
        targetScale = originalScale;
    }

    void OnEnable()
    {
        // Reset khi object được bật lại
        transform.localScale = originalScale;
        targetScale = originalScale;
    }
}