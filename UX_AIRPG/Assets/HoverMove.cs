using UnityEngine;
using UnityEngine.EventSystems;

public class HoverMove : MonoBehaviour, IPointerEnterHandler, IPointerExitHandler
{
    private Vector3 originalPos;
    private Vector3 targetPos;

    public float moveDistance = 40f;
    public float speed = 10f;

    void Awake()
    {
        // Lưu vị trí gốc sớm
        originalPos = transform.localPosition;
        targetPos = originalPos;
    }

    void Update()
    {
        transform.localPosition = Vector3.Lerp(transform.localPosition, targetPos, Time.deltaTime * speed);
    }

    public void OnPointerEnter(PointerEventData eventData)
    {
        targetPos = originalPos + new Vector3(moveDistance, 0, 0);
    }

    public void OnPointerExit(PointerEventData eventData)
    {
        targetPos = originalPos;
    }

    void OnEnable()
    {
        // Reset khi bật lại object
        transform.localPosition = originalPos;
        targetPos = originalPos;
    }
}