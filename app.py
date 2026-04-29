import streamlit as st
import requests
import time
import anthropic

# ─────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="MTG AI Deck Builder",
    page_icon="🐉",
    layout="wide"
)

# ─────────────────────────────────────────────
# Custom CSS for a cleaner look
# ─────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        text-align: center;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0;
    }
    .sub-title {
        text-align: center;
        font-size: 1.1rem;
        color: #888;
        margin-top: 0;
    }
    .card-grid img {
        border-radius: 12px;
    }
    .stButton>button {
        width: 100%;
        background-color: #6C3483;
        color: white;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Title
# ─────────────────────────────────────────────
st.markdown('<p class="main-title">🐉 MTG AI Deck Builder 🧙‍♂️</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Pick a tribe. Pick a format. Let AI build you a killer deck.</p>', unsafe_allow_html=True)
st.markdown("---")

# ─────────────────────────────────────────────
# Initialize session state
# ─────────────────────────────────────────────
if "deck_result" not in st.session_state:
    st.session_state.deck_result = None
if "card_images" not in st.session_state:
    st.session_state.card_images = {}

# ─────────────────────────────────────────────
# Sidebar — User Inputs
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Deck Settings")
    st.markdown("---")

    creature_type = st.text_input(
        "🦎 Creature / Card Type",
        placeholder="e.g., Dragons, Wizards, Elves, Zombies...",
        help="Enter any MTG creature type or tribal theme."
    )

    format_choice = st.selectbox(
        "📜 Format",
        ["Commander", "Modern", "Standard", "Pioneer", "Pauper"],
        help="Choose which MTG format the deck should be legal in."
    )

    strategy = st.selectbox(
        "🎯 Strategy Preference",
        ["Aggressive", "Midrange", "Control", "Combo"],
        help="What play style do you want?"
    )

    budget = st.selectbox(
        "💰 Budget",
        ["No Limit", "Budget ($50 or less)", "Mid-range ($50–$150)"],
        help="Set a budget constraint for the deck."
    )

    st.markdown("---")
    build_button = st.button("🚀 Build My Deck!", use_container_width=True)

# ─────────────────────────────────────────────
# Scryfall Search Function
# ─────────────────────────────────────────────
def search_scryfall(creature_type, format_choice):
    """
    Search the Scryfall API for cards matching the creature type
    and format legality. Returns up to 300 cards.
    """
    fmt = format_choice.lower()
    query = f"t:{creature_type} f:{fmt}"

    url = "https://api.scryfall.com/cards/search"
    params = {"q": query, "order": "edhrec", "unique": "cards"}

    all_cards = []

    try:
        while url and len(all_cards) < 300:
            response = requests.get(url, params=params)

            if response.status_code == 404:
                return []

            response.raise_for_status()
            data = response.json()

            for card in data.get("data", []):
                # Get image URL (handle double-faced cards)
                image_url = None
                if "image_uris" in card:
                    image_url = card["image_uris"].get("normal")
                elif "card_faces" in card and len(card["card_faces"]) > 0:
                    face = card["card_faces"][0]
                    if "image_uris" in face:
                        image_url = face["image_uris"].get("normal")

                # Get oracle text (handle double-faced cards)
                oracle = card.get("oracle_text", "")
                if not oracle and "card_faces" in card:
                    oracle = " // ".join(
                        f.get("oracle_text", "") for f in card["card_faces"]
                    )

                all_cards.append({
                    "name": card.get("name", "Unknown"),
                    "mana_cost": card.get("mana_cost", ""),
                    "cmc": card.get("cmc", 0),
                    "type_line": card.get("type_line", ""),
                    "oracle_text": oracle,
                    "colors": card.get("colors", []),
                    "color_identity": card.get("color_identity", []),
                    "rarity": card.get("rarity", ""),
                    "price_usd": card.get("prices", {}).get("usd", "N/A"),
                    "image_url": image_url,
                    "set_name": card.get("set_name", ""),
                })

            # Handle pagination
            if data.get("has_more"):
                url = data.get("next_page")
                params = {}  # next_page URL already has params
                time.sleep(0.1)  # Respect rate limits
            else:
                break

    except requests.exceptions.RequestException as e:
        st.error(f"❌ Error searching Scryfall: {e}")
        return []

    return all_cards

# ─────────────────────────────────────────────
# Format card data for the AI prompt
# ─────────────────────────────────────────────
def format_card_data(cards):
    """Convert card list into a condensed text summary for the AI."""
    lines = []
    for c in cards:
        price_str = f"${c['price_usd']}" if c['price_usd'] != "N/A" else "N/A"
        lines.append(
            f"- {c['name']} | {c['mana_cost']} | {c['type_line']} | "
            f"{c['oracle_text'][:150]} | Price: {price_str}"
        )
    return "\n".join(lines)

# ─────────────────────────────────────────────
# AI Deck Builder Function (Claude)
# ─────────────────────────────────────────────
def build_deck_with_ai(card_text, creature_type, format_choice, strategy, budget):
    """Send card data to Anthropic Claude and get a complete decklist back."""

    deck_size = 100 if format_choice == "Commander" else 60
    commander_note = ""
    if format_choice == "Commander":
        commander_note = (
            "- Pick the BEST commander for this tribe and list it separately at the top.\n"
            "- The deck must be exactly 100 cards (including the commander).\n"
            "- All cards must share the commander's color identity.\n"
        )

    system_prompt = (
        "You are an expert Magic: The Gathering deck builder with deep knowledge of "
        "competitive meta, card synergies, mana curves, and winning strategies across "
        "all formats. You build optimized, tournament-ready tribal decks."
    )

    user_prompt = f"""Build me a {format_choice} deck focused on **{creature_type}** tribal.

**Strategy:** {strategy}
**Budget:** {budget}
**Deck Size:** {deck_size} cards

{commander_note}

Here are {creature_type}-related cards I found that are legal in {format_choice}:

{card_text}

**IMPORTANT INSTRUCTIONS:**
1. Use cards from the list above as the tribal core.
2. ALSO include essential cards NOT on this list — staple lands, removal, ramp, card draw,
   and utility cards that every good {format_choice} {strategy} deck needs.
3. Make sure the mana curve is smooth and the deck is actually playable and competitive.
4. Consider the current meta when making choices.

**FORMAT YOUR RESPONSE EXACTLY LIKE THIS:**

## 👑 Commander (if Commander format)
- [Card Name]

## 🗡️ Decklist

### Creatures (X)
- 1x Card Name
- 1x Card Name

### Instants (X)
- 1x Card Name

### Sorceries (X)
- 1x Card Name

### Enchantments (X)
- 1x Card Name

### Artifacts (X)
- 1x Card Name

### Planeswalkers (X)
- 1x Card Name

### Lands (X)
- 1x Card Name

## 🧠 Strategy Explanation
[2-3 paragraphs explaining how the deck works, its game plan, and how to pilot it]

## 🔗 Key Synergies
- [Synergy 1: Card A + Card B — explanation]
- [Synergy 2: Card C + Card D — explanation]
- [Synergy 3: etc.]
"""

    try:
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0.7,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        return response.content[0].text

    except Exception as e:
        st.error(
            f"❌ Claude API Error: {e}\n\n"
            "**Make sure your ANTHROPIC_API_KEY is set correctly in Streamlit secrets.**"
        )
        return None

# ─────────────────────────────────────────────
# Main Logic — When "Build My Deck!" is clicked
# ─────────────────────────────────────────────
if build_button:
    if not creature_type.strip():
        st.warning("⚠️ Please enter a creature type in the sidebar!")
    else:
        # Step 1: Search Scryfall
        with st.spinner(f"🔍 Searching Scryfall for {creature_type} cards..."):
            cards = search_scryfall(creature_type, format_choice)

        if not cards:
            st.warning(
                f"⚠️ No **{creature_type}** cards found for **{format_choice}** format. "
                "Try a different creature type or format."
            )
        else:
            st.success(f"✅ Found **{len(cards)}** {creature_type} cards! Sending to AI...")

            # Store images for later display
            st.session_state.card_images = {
                c["name"]: c["image_url"] for c in cards if c["image_url"]
            }

            # Step 2: Format card data
            card_text = format_card_data(cards)

            # Step 3: Build deck with AI
            with st.spinner("🤖 Claude is brewing your deck... This may take 15–30 seconds."):
                result = build_deck_with_ai(
                    card_text, creature_type, format_choice, strategy, budget
                )

            if result:
                st.session_state.deck_result = result

# ─────────────────────────────────────────────
# Display Results (persists via session state)
# ─────────────────────────────────────────────
if st.session_state.deck_result:
    st.markdown("---")
    st.markdown("## 📋 Your AI-Generated Deck")
    st.markdown(st.session_state.deck_result)

    # ─────────────────────────────────────────
    # Export Decklist Button
    # ─────────────────────────────────────────
    st.markdown("---")
    st.download_button(
        label="📥 Download Decklist as Text File",
        data=st.session_state.deck_result,
        file_name="mtg_deck.txt",
        mime="text/plain",
        use_container_width=True
    )

    # ─────────────────────────────────────────
    # Card Image Gallery
    # ─────────────────────────────────────────
    if st.session_state.card_images:
        st.markdown("---")
        st.markdown("## 🖼️ Card Gallery (Tribal Cards Found)")
        st.caption("Showing card images from the Scryfall search results used by the AI.")

        # Display in a 4-column grid
        image_items = list(st.session_state.card_images.items())[:40]
        cols = st.columns(4)
        for idx, (name, url) in enumerate(image_items):
            with cols[idx % 4]:
                st.image(url, caption=name, use_container_width=True)

# ─────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #888; font-size: 0.85rem;">
        <p>⚡ Powered by <b>Scryfall API</b> + <b>Anthropic Claude</b> + <b>Streamlit</b></p>
        <p>🔑 This app requires an Anthropic API key. Get one at
        <a href="https://console.anthropic.com/" target="_blank">console.anthropic.com</a></p>
        <p>Card data © Wizards of the Coast. Card images courtesy of Scryfall.</p>
    </div>
    """,
    unsafe_allow_html=True
)
