let _currentAlertId = null;

const evtSource = new EventSource("/api/auction/stream");
evtSource.onmessage = function(e) {
  showAuctionPopup(JSON.parse(e.data));
};

function showAuctionPopup(data) {
  _currentAlertId = data.id;
  document.getElementById("au-name").textContent = data.stock_name || "-";
  document.getElementById("au-code").textContent = data.stock_code;
  const actionEl = document.getElementById("au-action");
  actionEl.textContent = data.suggested_action === "buy" ? "매수 추천" : "매도 추천";
  actionEl.className = "badge " + (data.suggested_action === "buy" ? "bg-primary" : "bg-danger");
  document.getElementById("au-price").textContent = Number(data.suggested_price).toLocaleString();
  document.getElementById("au-qty").textContent = data.suggested_qty;
  document.getElementById("au-expires").textContent = data.expires_at.replace("T", " ").slice(0, 19);
  document.getElementById("auction-overlay").classList.add("show");
}

function auctionDecide(decision) {
  if (!_currentAlertId) return;
  fetch("/api/auction/decide/" + _currentAlertId, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  })
    .then(r => r.json())
    .then(d => {
      document.getElementById("auction-overlay").classList.remove("show");
      _currentAlertId = null;
      if (d.message) alert(d.message);
    })
    .catch(() => alert("처리 실패"));
}

// 페이지 로드 시 미결 알림 확인
fetch("/api/auction/pending")
  .then(r => r.json())
  .then(list => { if (list.length > 0) showAuctionPopup(list[0]); });
