using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
using TMPro;
using System.Collections;
using System;
using System.Diagnostics;

[Serializable]
public class GameResponse { 
    public string speaker; 
    public string story; 
    public string[] choices; 
    public string bg_image_b64; 
    public string char_image_b64; 
    public string message; 
    public string error;
}

public class GameClient : MonoBehaviour
{
    public string serverUrl = "http://localhost:8000/api"; 
    
    [Header("UI Panels")]
    public GameObject mainMenuPanel;
    public GameObject gamePanel;
    public GameObject loadingPanel;
    public GameObject inventoryPanel; 
    public GameObject settingPanel; // 🌟 Panel Cài đặt mới

    [Header("Game Elements")]
    public RawImage backgroundImage;
    public RawImage characterImage;
    public TextMeshProUGUI speakerText;
    public TextMeshProUGUI storyText;
    
    [Header("Choices UI")]
    public Button[] choiceButtons;     
    public TextMeshProUGUI[] choiceTexts; 

    [Header("Hideable UI (Để ngắm ảnh)")]
    public GameObject[] uiElementsToHide; 
    private bool isUIHidden = false;

    private string[] currentChoices;
    private Coroutine tempMessageCoroutine; 

    private Process _backendProcess;
    private bool isBackendReady = false;

    // --- KHỞI ĐỘNG BACKEND ---
    private void StartBackend()
    {
        try {
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = "python"; 
            startInfo.Arguments = "main.py"; 
            startInfo.CreateNoWindow = true; 
            startInfo.UseShellExecute = false;
            startInfo.WorkingDirectory = Application.dataPath + "/../"; 

            _backendProcess = Process.Start(startInfo);
            UnityEngine.Debug.Log("🧠 Đang gọi bộ não AI...");
        } catch (System.Exception e) {
            UnityEngine.Debug.LogError("❌ Không thể gọi Python: " + e.Message);
        }
    }

    private void OnApplicationQuit()
    {
        if (_backendProcess != null && !_backendProcess.HasExited)
        {
            _backendProcess.Kill();
            _backendProcess.Dispose();
            UnityEngine.Debug.Log("🛑 Đã tắt Backend.");
        }
    }

    private void Start()
    {
        StartBackend();

        // Trạng thái ban đầu
        mainMenuPanel.SetActive(true);
        gamePanel.SetActive(false);
        loadingPanel.SetActive(false);
        if (inventoryPanel != null) inventoryPanel.SetActive(false);
        if (settingPanel != null) settingPanel.SetActive(false); // Ẩn setting lúc đầu
    }

    // ==========================================
    // 1. CÁC HÀM CHO MAIN MENU & SETTING
    // ==========================================
    public void OnClickToggleSetting() // 🌟 Hàm bật/tắt Setting
    {
        if (settingPanel != null)
        {
            settingPanel.SetActive(!settingPanel.activeSelf);
            // Nếu mở Setting thì nên đóng Inventory cho đỡ rối
            if (settingPanel.activeSelf && inventoryPanel != null) inventoryPanel.SetActive(false);
        }
    }

    public void OnClickNewGame()
    {
        mainMenuPanel.SetActive(false);
        gamePanel.SetActive(true);
        if (settingPanel != null) settingPanel.SetActive(false); // Đóng setting khi vào game
        characterImage.gameObject.SetActive(false);
        SetUIState(true);
        StartCoroutine(PostRequest("/new_game", "")); 
    }

    public void OnClickLoadGame()
    {
        mainMenuPanel.SetActive(false);
        gamePanel.SetActive(true);
        if (settingPanel != null) settingPanel.SetActive(false);
        StartCoroutine(PostRequest("/load_game", ""));
    }

    public void OnClickExit()
    {
        Application.Quit();
    }

    // ==========================================
    // 2. CÁC HÀM TRONG LÚC CHƠI
    // ==========================================
    public void OnClickHome()
    {
        gamePanel.SetActive(false);
        mainMenuPanel.SetActive(true);
        if (settingPanel != null) settingPanel.SetActive(false);
        if (inventoryPanel != null) inventoryPanel.SetActive(false);
    }

    public void OnClickSaveGame()
    {
        StartCoroutine(PostRequest("/save_game", ""));
    }

    public void OnClickChoice(int choiceIndex)
    {
        if (currentChoices == null || choiceIndex >= currentChoices.Length) return;
        string selectedAction = currentChoices[choiceIndex];
        StartCoroutine(PostRequest("/play", selectedAction));
    }

    private void SetUIState(bool isHidden)
    {
        isUIHidden = isHidden;
        foreach (GameObject obj in uiElementsToHide)
        {
            if (obj != null) obj.SetActive(!isUIHidden);
        }
    }

    public void OnClickToggleUI()
    {
        SetUIState(!isUIHidden);
    }

    public void OnClickToggleInventory()
    {
        if (inventoryPanel != null)
        {
            inventoryPanel.SetActive(!inventoryPanel.activeSelf);
            // Nếu mở Inventory thì đóng Setting
            if (inventoryPanel.activeSelf && settingPanel != null) settingPanel.SetActive(false);
        }
    }

    private IEnumerator ShowTemporaryMessage(string message, float duration)
    {
        string oldSpeaker = speakerText.text;
        string oldStory = storyText.text;
        speakerText.text = "[Hệ thống]";
        storyText.text = message;
        yield return new WaitForSeconds(duration);
        speakerText.text = oldSpeaker;
        storyText.text = oldStory;
    }

    // ==========================================
    // 3. LÕI GIAO TIẾP SERVER
    // ==========================================
    private IEnumerator PostRequest(string endpoint, string action)
    {
        loadingPanel.SetActive(true);
        foreach (var btn in choiceButtons) btn.gameObject.SetActive(false);

        WWWForm form = new WWWForm();
        if (!string.IsNullOrEmpty(action)) form.AddField("action", action);

        using (UnityWebRequest www = UnityWebRequest.Post(serverUrl + endpoint, form))
        {
            yield return www.SendWebRequest();
            loadingPanel.SetActive(false);
            SetUIState(false);

            if (www.result != UnityWebRequest.Result.Success)
            {
                speakerText.text = "[Hệ thống]";
                storyText.text = "Lỗi kết nối Backend: " + www.error;
            }
            else
            {
                string jsonResult = www.downloadHandler.text;
                GameResponse response = JsonUtility.FromJson<GameResponse>(jsonResult);
                
                if (endpoint == "/save_game")
                {
                    SetUIState(false);
                    string msg = response.message != null ? response.message : "Đã lưu game!";
                    if (tempMessageCoroutine != null) StopCoroutine(tempMessageCoroutine);
                    tempMessageCoroutine = StartCoroutine(ShowTemporaryMessage(msg, 2.5f));
                    if (currentChoices != null) {
                        for (int i = 0; i < currentChoices.Length; i++) {
                            if(i < choiceButtons.Length) choiceButtons[i].gameObject.SetActive(true);
                        }
                    }
                    yield break; 
                }

                if (response.story != null) storyText.text = response.story;
                speakerText.text = string.IsNullOrEmpty(response.speaker) ? "[Game Master]" : $"[{response.speaker}]";

                if (response.choices != null && response.choices.Length > 0)
                {
                    currentChoices = response.choices;
                    for (int i = 0; i < choiceButtons.Length; i++)
                    {
                        if (i < currentChoices.Length)
                        {
                            choiceButtons[i].gameObject.SetActive(true);
                            choiceTexts[i].text = currentChoices[i];
                        }
                    }
                }
                else 
                {
                    currentChoices = new string[] { "Tiếp tục" };
                    choiceButtons[0].gameObject.SetActive(true);
                    choiceTexts[0].text = "Tiếp tục";
                }

                if (!string.IsNullOrEmpty(response.bg_image_b64)) {
                    Texture2D bgTex = new Texture2D(2, 2);
                    bgTex.LoadImage(Convert.FromBase64String(response.bg_image_b64));
                    backgroundImage.texture = bgTex;
                }
                
                if (!string.IsNullOrEmpty(response.char_image_b64)) {
                    characterImage.gameObject.SetActive(true);
                    Texture2D charTex = new Texture2D(2, 2);
                    charTex.LoadImage(Convert.FromBase64String(response.char_image_b64));
                    characterImage.texture = charTex;
                    AspectRatioFitter fitter = characterImage.GetComponent<AspectRatioFitter>();
                    if (fitter != null) fitter.aspectRatio = (float)charTex.width / (float)charTex.height;
                } else {
                    characterImage.gameObject.SetActive(false); 
                }
            }
        }
    }
}