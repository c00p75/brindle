"use client";

import React from "react";
import { BrokerAccountBalance } from "@/lib/types";

interface Props {
  balances: BrokerAccountBalance[];
  loading?: boolean;
}

export default function BrokerBalancesCard({ balances, loading }: Props) {
  if (!loading && balances.length === 0) return null;

  return (
    <div style={cardStyle}>
      <div style={headerStyle}>
        <div style={titleWrap}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="5" width="20" height="14" rx="2" />
            <line x1="2" y1="10" x2="22" y2="10" />
          </svg>
          <h2 style={titleStyle}>Connected Broker Balances</h2>
        </div>
        <div style={badgeStyle}>{balances.length} Accounts</div>
      </div>

      <div style={listStyle}>
        {loading ? (
          <div style={loadingPlaceholder}>
            <div className="shimmer" style={{ height: 60, borderRadius: 8, background: "#f8f9fa" }} />
          </div>
        ) : (
          balances.map((bb, i) => (
            <div key={`${bb.broker_type}-${bb.account_id}`} style={{
              ...rowStyle,
              borderBottom: i === balances.length - 1 ? "none" : "1px solid #f2f3f4"
            }}>
              <div style={infoCol}>
                <div style={brokerLabel}>
                  <span style={typeBadge}>{bb.broker_type}</span>
                  <span style={envPill(bb.environment)}>{bb.environment}</span>
                </div>
                <div style={accountId}>{bb.account_id}</div>
              </div>
              
              <div style={balanceCol}>
                {bb.error ? (
                  <div style={errorLabel} title={bb.error}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                    Error
                  </div>
                ) : (
                  <>
                    <div style={amountStyle}>
                      <span style={currencyStyle}>{bb.currency === "USD" ? "$" : bb.currency}</span>
                      {bb.available?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div style={statusStyle}>
                      <div style={dotStyle} />
                      Connected
                    </div>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <style jsx>{`
        .shimmer {
          background: linear-gradient(90deg, #f8f9fa 25%, #f1f3f5 50%, #f8f9fa 75%);
          background-size: 200% 100%;
          animation: shimmer 1.5s infinite;
        }
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: "12px",
  border: "1px solid #e8eaeb",
  boxShadow: "0 4px 20px rgba(0, 0, 0, 0.04)",
  overflow: "hidden",
  marginBottom: "24px",
};

const headerStyle: React.CSSProperties = {
  padding: "16px 20px",
  borderBottom: "1px solid #f2f3f4",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  background: "linear-gradient(to right, #fcfdfe, #fff)",
};

const titleWrap: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
};

const titleStyle: React.CSSProperties = {
  fontSize: "15px",
  fontWeight: 700,
  color: "#0e0e0e",
  margin: 0,
};

const badgeStyle: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 800,
  color: "#4f46e5",
  background: "#f0efff",
  padding: "4px 8px",
  borderRadius: "6px",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const listStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
};

const rowStyle: React.CSSProperties = {
  padding: "16px 20px",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  transition: "background 0.15s",
};

const infoCol: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const brokerLabel: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
};

const typeBadge: React.CSSProperties = {
  fontSize: "13px",
  fontWeight: 700,
  color: "#0e0e0e",
  textTransform: "capitalize",
};

const envPill = (env: string): React.CSSProperties => ({
  fontSize: "9px",
  fontWeight: 800,
  padding: "2px 6px",
  borderRadius: "4px",
  textTransform: "uppercase",
  letterSpacing: "0.03em",
  background: env === "live" ? "#fff0f0" : "#edfaf7",
  color: env === "live" ? "#cc2626" : "#008265",
  border: `1px solid ${env === "live" ? "#fecaca" : "#bbf7d0"}`,
});

const accountId: React.CSSProperties = {
  fontSize: "11px",
  color: "#868e96",
  fontFamily: "var(--font-mono, monospace)",
};

const balanceCol: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "flex-end",
  gap: "2px",
};

const amountStyle: React.CSSProperties = {
  fontSize: "20px",
  fontWeight: 700,
  color: "#0e0e0e",
  letterSpacing: "-0.02em",
};

const currencyStyle: React.CSSProperties = {
  fontSize: "14px",
  color: "#868e96",
  marginRight: "2px",
  fontWeight: 500,
};

const statusStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "5px",
  fontSize: "10px",
  fontWeight: 700,
  color: "#008265",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const dotStyle: React.CSSProperties = {
  width: "6px",
  height: "6px",
  borderRadius: "50%",
  background: "#008265",
  boxShadow: "0 0 0 2px rgba(0, 130, 101, 0.15)",
};

const errorLabel: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "4px",
  fontSize: "12px",
  fontWeight: 700,
  color: "#cc2626",
  background: "#fff0f0",
  padding: "4px 10px",
  borderRadius: "6px",
};

const loadingPlaceholder: React.CSSProperties = {
  padding: "20px",
};
