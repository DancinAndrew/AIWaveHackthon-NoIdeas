import { useEffect, useState } from "react";

// 後端回傳資料型別
interface TestResponse {
  status: string;
  message: string;
}

const API_BASE_URL = "http://localhost:8000";

export default function ApiTestComponent() {
  const [loading, setLoading] = useState<boolean>(true);
  const [data, setData] = useState<TestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTest = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/test`);

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        const json: TestResponse = await res.json();
        setData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };

    fetchTest();
  }, []);

  if (loading) {
    return <p style={{ color: "#888", fontSize: "1.2rem" }}>Loading...</p>;
  }

  if (error) {
    return (
      <div style={{ color: "#e74c3c", padding: "1rem", borderLeft: "4px solid #e74c3c" }}>
        <strong>Error:</strong> {error}
      </div>
    );
  }

  return (
    <div style={{ padding: "1.5rem", borderLeft: "4px solid #2ecc71", background: "#f0fff4" }}>
      <p style={{ fontSize: "1.4rem", fontWeight: 600, color: "#27ae60", margin: 0 }}>
        {data?.message}
      </p>
      <p style={{ fontSize: "0.9rem", color: "#888", marginTop: "0.5rem" }}>
        Status: {data?.status}
      </p>
    </div>
  );
}
