export default function App() {
  return (
    <div style={{
      fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
      background: "linear-gradient(135deg, #0f2027, #203a43, #2c5364)",
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      color: "#fff",
      margin: 0,
    }}>
      {/* Header */}
      <header style={{
        width: "100%",
        background: "rgba(0,0,0,0.35)",
        padding: "18px 32px",
        display: "flex",
        alignItems: "center",
        gap: 16,
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        boxSizing: "border-box",
      }}>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, margin: 0 }}>
            Awche Lottery
          </h1>
          <span style={{ fontSize: "0.85rem", color: "#ffd700", fontWeight: 600 }}>
            <span style={{
              display: "inline-block", width: 8, height: 8,
              background: "#4caf50", borderRadius: "50%", marginRight: 6,
            }} />
            Bot Online &amp; Accepting Registrations
          </span>
        </div>
      </header>

      {/* Hero */}
      <div style={{
        textAlign: "center",
        padding: "60px 24px 40px",
        maxWidth: 680,
        width: "100%",
        boxSizing: "border-box",
      }}>
        <div style={{
          display: "inline-block",
          background: "#ffd700",
          color: "#1a1a1a",
          fontWeight: 700,
          fontSize: "0.78rem",
          padding: "4px 14px",
          borderRadius: 20,
          letterSpacing: "1px",
          textTransform: "uppercase",
          marginBottom: 20,
        }}>
          Official Registration
        </div>

        <h2 style={{ fontSize: "2.4rem", fontWeight: 800, lineHeight: 1.2, margin: "0 0 16px" }}>
          Register for the<br />
          <span style={{ color: "#ffd700" }}>Lucky Draw</span>
        </h2>

        <p style={{
          fontSize: "1.05rem",
          color: "rgba(255,255,255,0.75)",
          lineHeight: 1.7,
          marginBottom: 32,
        }}>
          Participate in the Awche Lottery by sending your CBE Mobile Banking
          receipt photo to our Telegram bot. Your Transaction ID is verified instantly
          against our records and you receive your lottery number right away.
        </p>

        <div style={{
          background: "rgba(255,215,0,0.12)",
          border: "1px solid rgba(255,215,0,0.35)",
          borderRadius: 12,
          padding: "16px 28px",
          display: "inline-block",
          marginBottom: 36,
        }}>
          <div style={{ fontSize: "0.78rem", color: "#ffd700", textTransform: "uppercase", letterSpacing: "1px" }}>
            Draw Date
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 800, marginTop: 4 }}>
            ሰኔ 5 / 2018 E.C.
          </div>
        </div>

        <br />

        <a
          href="https://t.me/+hNcPdZTTL-xhMjhk"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 10,
            background: "#229ED9",
            color: "#fff",
            fontSize: "1.05rem",
            fontWeight: 700,
            padding: "16px 36px",
            borderRadius: 50,
            textDecoration: "none",
            boxShadow: "0 4px 24px rgba(34,158,217,0.45)",
          }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.247-1.97 9.289c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.932z" />
          </svg>
          Register via Telegram Bot
        </a>
      </div>

      {/* Steps */}
      <div style={{
        width: "100%",
        maxWidth: 820,
        padding: "0 24px 60px",
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        gap: 20,
        boxSizing: "border-box",
      }}>
        {[
          { icon: "📸", title: "Step 1 — Send Receipt", desc: "Open the bot and send a photo of your CBE Mobile Banking payment receipt, or type your Transaction ID manually." },
          { icon: "✅", title: "Step 2 — Verify", desc: "The bot reads your Transaction ID automatically using OCR and checks it against our verified payment records." },
          { icon: "🎟️", title: "Step 3 — Get Your Number", desc: "Once confirmed, your name and mobile number are saved and you instantly receive your unique lottery number." },
          { icon: "📺", title: "Step 4 — Watch the Draw", desc: "Follow our Telegram, YouTube, TikTok, or Facebook on draw day — ሰኔ 5/2018 — to see if your number wins!" },
        ].map((step) => (
          <div key={step.title} style={{
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 16,
            padding: "28px 24px",
            textAlign: "center",
          }}>
            <div style={{ fontSize: "2rem", marginBottom: 14 }}>{step.icon}</div>
            <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: 8, color: "#ffd700", margin: "0 0 8px" }}>
              {step.title}
            </h3>
            <p style={{ fontSize: "0.88rem", color: "rgba(255,255,255,0.65)", lineHeight: 1.6, margin: 0 }}>
              {step.desc}
            </p>
          </div>
        ))}
      </div>

      {/* Social links */}
      <div style={{
        display: "flex",
        gap: 16,
        justifyContent: "center",
        padding: "0 24px 48px",
        flexWrap: "wrap",
      }}>
        {[
          { href: "https://t.me/+hNcPdZTTL-xhMjhk", label: "✈️ Telegram" },
          { href: "https://youtube.com/@awuchetube?si=gS48mTKirCFoFSRK", label: "▶️ YouTube" },
          { href: "https://www.tiktok.com/@awuch66", label: "🎵 TikTok" },
          { href: "http://facebook.com/share/1DwpPzF9bQ", label: "📘 Facebook" },
        ].map((s) => (
          <a key={s.href} href={s.href} target="_blank" rel="noopener noreferrer" style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            background: "rgba(255,255,255,0.08)",
            border: "1px solid rgba(255,255,255,0.15)",
            color: "#fff",
            textDecoration: "none",
            padding: "10px 20px",
            borderRadius: 50,
            fontSize: "0.88rem",
            fontWeight: 600,
          }}>
            {s.label}
          </a>
        ))}
      </div>

      {/* Footer */}
      <footer style={{
        width: "100%",
        textAlign: "center",
        padding: 20,
        fontSize: "0.8rem",
        color: "rgba(255,255,255,0.35)",
        borderTop: "1px solid rgba(255,255,255,0.08)",
        boxSizing: "border-box",
      }}>
        &copy; 2025 Awche Lottery — All rights reserved
      </footer>
    </div>
  );
}
