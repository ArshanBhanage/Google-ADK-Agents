import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
type Product = {
  product_id: string;
  variant_id: string;
  title: string;
  variant_title: string;
  amount: string;
  currency: string;
  available: boolean;
  image_url?: string;
  catalog_synced_at: string;
};
type Line = {
  id: string;
  quantity: number;
  merchandise: { id: string; title: string; product: { title: string } };
};
type Cart = {
  id?: string;
  lines?: Line[];
  cost?: { totalAmount: { amount: string; currencyCode: string } };
};
function App() {
  const [token, setToken] = useState(""),
    [signed, setSigned] = useState(false),
    [query, setQuery] = useState(""),
    [items, setItems] = useState<Product[]>([]),
    [cart, setCart] = useState<Cart>({}),
    [message, setMessage] = useState(""),
    [answer, setAnswer] = useState(""),
    [trace, setTrace] = useState<string[]>([]),
    [status, setStatus] = useState(
      "Connect to browse your merchant’s catalog.",
    ),
    [busy, setBusy] = useState(false),
    [checkout, setCheckout] = useState("");
  async function api(path: string, body?: unknown) {
    const r = await fetch("/api/" + path, {
      method: body ? "POST" : "GET",
      headers: {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json();
    if (!r.ok)
      throw Error(
        typeof data.detail === "string"
          ? data.detail
          : "Request could not be completed",
      );
    return data;
  }
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setStatus("Working…");
    try {
      await fn();
      setStatus("Updated from your merchant.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  async function action(kind: string, extra: Record<string, unknown> = {}) {
    if (
      !window.confirm(
        kind === "checkout"
          ? "Get a Shopify checkout link? No payment will be made here."
          : `Confirm ${kind} cart action?`,
      )
    )
      return;
    await run(async () => {
      let active = cart;
      if (kind === "add" && !active.id) {
        active = await api("cart/actions", {
          action: "create",
          request_id: crypto.randomUUID(),
          confirmed: true,
        });
        setCart(active);
      }
      const result = await api("cart/actions", {
        action: kind,
        request_id: crypto.randomUUID(),
        confirmed: true,
        ...(active.id ? { cart_id: active.id } : {}),
        ...extra,
      });
      if (kind === "checkout") {
        setCheckout(result.checkout_url);
      } else {
        setCart(result);
        setCheckout("");
      }
    });
  }
  return (
    <>
      <header>
        <a className="brand" href="/">
          MERCHANT<span> / assisted shopping</span>
        </a>
        <span className="badge">LIVE SHOPIFY CATALOG</span>
      </header>
      <main>
        <section className="hero">
          <p className="eyebrow">A clearer way to find what you need</p>
          <h1>
            Your catalog.
            <br />
            <em>A little guidance.</em>
          </h1>
          <p>
            Discover products with an AI assistant, check current availability,
            and finish securely with Shopify.
          </p>
        </section>
        {!signed ? (
          <section className="login panel">
            <h2>Connect your local account</h2>
            <p>
              Enter your personal access token. It stays in this tab’s memory
              and is cleared when you sign out.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run(async () => {
                  await api("me");
                  setSigned(true);
                  setCart(await api("cart"));
                });
              }}
            >
              <label>
                Access token
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                  autoComplete="off"
                />
              </label>
              <button disabled={busy}>Connect</button>
            </form>
          </section>
        ) : (
          <>
            <div className="session">
              <span>Private shopping session</span>
              <button
                className="quiet"
                onClick={() => {
                  setToken("");
                  setSigned(false);
                  setItems([]);
                  setCart({});
                  setAnswer("");
                  setCheckout("");
                }}
              >
                Sign out
              </button>
            </div>
            <div className="workspace">
              <section>
                <div className="panel assistant">
                  <p className="eyebrow">VERTEX AI + MCP</p>
                  <h2>What are you looking for?</h2>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      run(async () => {
                        const r = await api("chat", { message });
                        setAnswer(r.answer);
                        setTrace(r.tools);
                      });
                    }}
                  >
                    <label className="sr">Ask the shopping assistant</label>
                    <textarea
                      aria-label="Ask the shopping assistant"
                      placeholder="Describe what you need…"
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      maxLength={2000}
                      required
                    />
                    <button disabled={busy}>Ask assistant ↗</button>
                  </form>
                  {answer && <div className="answer">{answer}</div>}
                  {trace.length > 0 && (
                    <p className="meta">
                      Verified tool calls: {trace.join(" → ")}
                    </p>
                  )}
                </div>
                <section className="catalog">
                  <div className="section-title">
                    <h2>Explore the catalog</h2>
                    <span>Merchant-sourced prices</span>
                  </div>
                  <form
                    className="search"
                    onSubmit={(e) => {
                      e.preventDefault();
                      run(async () => {
                        const r = await api(
                          "catalog?query=" + encodeURIComponent(query),
                        );
                        setItems(r.products);
                      });
                    }}
                  >
                    <input
                      aria-label="Search catalog"
                      placeholder="Search a product or category"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      required
                      maxLength={300}
                    />
                    <button disabled={busy}>Search</button>
                  </form>
                  <div className="products">
                    {items.map((p) => (
                      <article className="product" key={p.variant_id}>
                        {p.image_url && (
                          <img
                            src={p.image_url}
                            alt={p.title}
                            loading="lazy"
                            referrerPolicy="no-referrer"
                          />
                        )}
                        <div className="product-body">
                          <span className="meta">{p.variant_title}</span>
                          <h3>{p.title}</h3>
                          <p className="price">
                            {p.amount} {p.currency}
                          </p>
                          <p className="meta">
                            {p.available
                              ? "Available at last sync"
                              : "Unavailable at last sync"}
                            <br />
                            Synced{" "}
                            {new Date(p.catalog_synced_at).toLocaleString()}
                          </p>
                          <button
                            disabled={busy || !p.available}
                            onClick={() =>
                              action("add", {
                                variant_id: p.variant_id,
                                quantity: 1,
                              })
                            }
                          >
                            Add one to cart +
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                  {items.length === 0 && (
                    <p className="empty">
                      Search to see matching products. We only show results
                      returned by your merchant’s catalog.
                    </p>
                  )}
                </section>
              </section>
              <aside className="panel cart">
                <p className="eyebrow">YOUR SELECTION</p>
                <h2>Shopping cart</h2>
                {!cart.lines?.length ? (
                  <p className="empty">Your cart is empty.</p>
                ) : (
                  cart.lines.map((l) => (
                    <div className="line" key={l.id}>
                      <strong>{l.merchandise.product.title}</strong>
                      <p>
                        {l.merchandise.title} · Qty {l.quantity}
                      </p>
                      <button
                        className="quiet"
                        disabled={busy}
                        onClick={() => action("remove", { line_id: l.id })}
                      >
                        Remove
                      </button>
                    </div>
                  ))
                )}
                {cart.cost && (
                  <p className="total">
                    Estimated total{" "}
                    <strong>
                      {cart.cost.totalAmount.amount}{" "}
                      {cart.cost.totalAmount.currencyCode}
                    </strong>
                  </p>
                )}
                <button
                  disabled={busy || !cart.lines?.length}
                  onClick={() => action("checkout")}
                >
                  Continue to Shopify ↗
                </button>
                {checkout && (
                  <a
                    className="checkout"
                    href={checkout}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open secure Shopify checkout ↗
                  </a>
                )}
                <p className="meta">
                  Availability is refreshed before handoff. Shopify confirms
                  final stock, shipping, taxes and payment.
                </p>
                <button
                  className="quiet"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      setCart(await api("cart"));
                      setCheckout("");
                    })
                  }
                >
                  Refresh cart
                </button>
                <hr />
                <p className="meta">
                  Order history is unavailable until customer-account
                  permissions are configured.
                </p>
              </aside>
            </div>
          </>
        )}
        <p className="status" role="status">
          {status}
        </p>
        <footer>
          Real products. Explicit approvals. Payment handled by Shopify.
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
