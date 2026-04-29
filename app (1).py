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
# Custom CSS
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
    }
    div[data-testid="stHorizontalBlock"] .stButton>button {
        background-color: #6C3483;
        color: white;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .config-box {
        background-color: #1a1a2e;
        border: 2px solid #6C3483;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Title
# ─────────────────────────────────────────────
st.markdown('<p class="main-title">🐉 MTG AI Deck Builder 🧙‍♂️</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Pick a card. Pick your colors. Let AI build you a killer deck.</p>', unsafe_allow_html=True)
st.markdown("---")

# ─────────────────────────────────────────────
# Initialize session state
# ─────────────────────────────────────────────
if "deck_result" not in st.session_state:
    st.session_state.deck_result = None
if "card_images" not in st.session_state:
    st.session_state.card_images = {}
if "selected_card" not in st.session_state:
    st.session_state.selected_card = None
if "show_config" not in st.session_state:
    st.session_state.show_config = False

# ─────────────────────────────────────────────
# Sidebar — User Inputs
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Deck Settings")
    st.markdown("---")

    # Platform Selection
    platform = st.radio(
        "🎮 Platform",
        ["Paper (Tabletop)", "MTG Arena (Digital)"],
        help="Paper uses real-world tournament meta. Arena uses digital-specific meta and Arena-legal cards."
    )
    is_arena = platform == "MTG Arena (Digital)"

    st.markdown("---")

    # Color Identity Selection
    st.subheader("🎨 Color Identity")
    col_w, col_u = st.columns(2)
    col_b, col_r = st.columns(2)
    col_g, _ = st.columns(2)

    with col_w:
        white = st.checkbox("⚪ White", value=False)
    with col_u:
        blue = st.checkbox("🔵 Blue", value=False)
    with col_b:
        black = st.checkbox("⚫ Black", value=False)
    with col_r:
        red = st.checkbox("🔴 Red", value=False)
    with col_g:
        green = st.checkbox("🟢 Green", value=False)

    selected_colors = []
    if white: selected_colors.append("W")
    if blue:  selected_colors.append("U")
    if black: selected_colors.append("B")
    if red:   selected_colors.append("R")
    if green: selected_colors.append("G")
    color_identity = "".join(selected_colors)

    st.markdown("---")

    creature_type = st.text_input(
        "🦎 Creature / Card Type (optional)",
        placeholder="e.g., Dragons, Wizards, Elves...",
        help="Leave blank to build around just the selected card or colors."
    )

    format_choice_sidebar = st.selectbox(
        "📜 Format",
        ["Commander", "Modern", "Standard", "Pioneer", "Pauper"],
        help="Choose which MTG format the deck should be legal in."
    )

    strategy_sidebar = st.selectbox(
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
    build_custom_button = st.button("🚀 Build Custom Deck", use_container_width=True)
    st.caption("Build a tribal/color deck without picking a specific card above.")

# ─────────────────────────────────────────────
# Helper: Normalize creature type (plural → singular)
# ─────────────────────────────────────────────
def normalize_creature_type(raw_input):
    """Convert 'Dragons' → 'dragon', 'Elves' → 'elf', etc."""
    text = raw_input.strip().lower()
    irregulars = {
        "wolves": "wolf", "werewolves": "werewolf", "elves": "elf",
        "dwarves": "dwarf", "fungi": "fungus", "sphinxes": "sphinx",
        "cyclopes": "cyclops",
    }
    if text in irregulars:
        return irregulars[text]
    if text.endswith("s") and len(text) > 3:
        return text[:-1]
    return text

# ─────────────────────────────────────────────
# Fetch Popular Legendary Creatures (cached)
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_popular_cards(color_filter="", arena_only=False):
    """
    Fetch top legendary creatures from Scryfall.
    Optionally filter by color identity and Arena legality.
    """
    query = "t:legendary t:creature f:commander"
    if color_filter:
        query += f" id<={color_filter}"
    if arena_only:
        query += " game:arena"

    url = "https://api.scryfall.com/cards/search"
    params = {"q": query, "order": "edhrec", "unique": "cards"}

    cards = []
    try:
        response = requests.get(url, params=params)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()

        for card in data.get("data", [])[:24]:
            image_url = None
            if "image_uris" in card:
                image_url = card["image_uris"].get("normal")
            elif "card_faces" in card and len(card["card_faces"]) > 0:
                face = card["card_faces"][0]
                if "image_uris" in face:
                    image_url = face["image_uris"].get("normal")

            oracle = card.get("oracle_text", "")
            if not oracle and "card_faces" in card:
                oracle = " // ".join(
                    f.get("oracle_text", "") for f in card["card_faces"]
                )

            color_map = {"W": "⚪", "U": "🔵", "B": "⚫", "R": "🔴", "G": "🟢"}
            ci = card.get("color_identity", [])
            color_symbols = " ".join(color_map.get(c, c) for c in ci) if ci else "Colorless"

            cards.append({
                "name": card.get("name", "Unknown"),
                "mana_cost": card.get("mana_cost", ""),
                "cmc": card.get("cmc", 0),
                "type_line": card.get("type_line", ""),
                "oracle_text": oracle,
                "color_identity": ci,
                "color_symbols": color_symbols,
                "rarity": card.get("rarity", ""),
                "price_usd": card.get("prices", {}).get("usd", "N/A"),
                "image_url": image_url,
                "set_name": card.get("set_name", ""),
            })

    except requests.exceptions.RequestException:
        return []

    return cards

# ─────────────────────────────────────────────
# Scryfall Search — Card Pool for Deck Building
# ─────────────────────────────────────────────
def search_scryfall(creature_type, format_choice, color_filter="", arena_only=False):
    """
    Search Scryfall for cards matching creature type, format, color identity,
    and platform. Returns up to 300 cards.
    """
    fmt = format_choice.lower()
    parts = []

    if creature_type.strip():
        singular = normalize_creature_type(creature_type)
        parts.append(f"(t:{singular} OR o:{singular})")

    parts.append(f"f:{fmt}")

    if color_filter:
        parts.append(f"id<={color_filter}")

    if arena_only:
        parts.append("game:arena")

    query = " ".join(parts)
    st.info(f"🔍 Searching Scryfall: `{query}`")

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
                image_url = None
                if "image_uris" in card:
                    image_url = card["image_uris"].get("normal")
                elif "card_faces" in card and len(card["card_faces"]) > 0:
                    face = card["card_faces"][0]
                    if "image_uris" in face:
                        image_url = face["image_uris"].get("normal")

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

            if data.get("has_more"):
                url = data.get("next_page")
                params = {}
                time.sleep(0.1)
            else:
                break

    except requests.exceptions.RequestException as e:
        st.error(f"❌ Error searching Scryfall: {e}")
        return []

    return all_cards

# ─────────────────────────────────────────────
# Format card data for AI prompt
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
def build_deck_with_ai(card_text, creature_type, format_choice, strategy, budget,
                       platform, card_name=None, card_info=None):
    """Send card data to Anthropic Claude and get a complete decklist back."""

    is_commander = format_choice == "Commander"
    deck_size = 100 if is_commander else 60

    # Platform-specific instructions
    if platform == "MTG Arena (Digital)":
        platform_note = (
            "**PLATFORM: MTG Arena (Digital)**\n"
            "- Only include cards available on MTG Arena.\n"
            "- Focus on the Arena-specific meta and popular ladder decks.\n"
            "- When discussing card acquisition, mention wildcard rarity costs "
            "(common, uncommon, rare, mythic) instead of dollar prices.\n"
            "- Consider Arena-specific formats like Best-of-One vs Best-of-Three.\n"
        )
    else:
        platform_note = (
            "**PLATFORM: Paper (Tabletop)**\n"
            "- Focus on real-world tournament meta and local game store play.\n"
            "- Consider card prices and availability.\n"
            "- Include cards from all legal sets for this format.\n"
        )

    # Build-around card instructions
    card_note = ""
    if card_name:
        if is_commander:
            card_note = (
                f"- The commander is **{card_name}**.\n"
                f"- Card details: {card_info}\n"
                f"- The deck must be exactly 100 cards (including the commander).\n"
                f"- All cards must share the commander's color identity.\n"
                f"- Build the deck to maximize synergy with this commander's abilities.\n"
            )
        else:
            card_note = (
                f"- Build the deck around **{card_name}** as the key card.\n"
                f"- Card details: {card_info}\n"
                f"- Include up to 4 copies of {card_name} in the deck.\n"
                f"- The entire deck strategy should support and synergize with this card.\n"
                f"- Deck size: {deck_size} cards.\n"
            )
    elif is_commander:
        card_note = (
            "- Pick the BEST commander for this deck and list it separately at the top.\n"
            "- The deck must be exactly 100 cards (including the commander).\n"
            "- All cards must share the commander's color identity.\n"
        )

    # Tribal note
    tribal_note = ""
    if creature_type.strip():
        tribal_note = f"The deck should have a **{creature_type}** tribal theme."

    system_prompt = (
        "You are an expert Magic: The Gathering deck builder with deep knowledge of "
        "competitive meta for both paper and digital (MTG Arena), card synergies, "
        "mana curves, and winning strategies across all formats. "
        "You build optimized, tournament-ready decks."
    )

    # Commander section label
    if is_commander:
        commander_section = "## 👑 Commander\n- [Commander Name]\n"
    else:
        commander_section = "## ⭐ Build-Around Card\n- [Card Name] (x4 or as appropriate)\n"

    user_prompt = f"""Build me a {format_choice} deck.

{tribal_note}

{platform_note}

**Strategy:** {strategy}
**Budget:** {budget}
**Deck Size:** {deck_size} cards

{card_note}

Here are relevant cards I found that are legal in {format_choice}:

{card_text}

**IMPORTANT INSTRUCTIONS:**
1. Use cards from the list above as the core of the deck.
2. ALSO include essential cards NOT on this list — staple lands, removal, ramp, card draw,
   and utility cards that every good {format_choice} {strategy} deck needs.
3. Make sure the mana curve is smooth and the deck is actually playable and competitive.
4. Consider the current {platform} meta when making choices.

**FORMAT YOUR RESPONSE EXACTLY LIKE THIS:**

{commander_section}

## 🗡️ Decklist

### Creatures (X)
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
[2-3 paragraphs explaining how the deck works, its game plan, and how to pilot it.
Include platform-specific tips (e.g., Arena best-of-one vs best-of-three, or paper sideboard tips).]

## 🔗 Key Synergies
- [Synergy 1: Card A + Card B — explanation]
- [Synergy 2: Card C + Card D — explanation]
- [Synergy 3: etc.]
"""

    try:
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

        response = client.messages.create(
            model="claude-sonnet-4-6",
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
# Core deck building logic (shared by both paths)
# ─────────────────────────────────────────────
def run_deck_build(selected_card=None, format_override=None, strategy_override=None):
    """
    Runs the full deck building pipeline.
    If selected_card is provided, builds around that card.
    format_override and strategy_override come from the config panel.
    """
    fmt = format_override if format_override else format_choice_sidebar
    strat = strategy_override if strategy_override else strategy_sidebar

    card_name = None
    card_info = None
    search_color = color_identity

    if selected_card:
        card_name = selected_card["name"]
        card_info = (
            f"{selected_card['name']} | {selected_card['mana_cost']} | "
            f"{selected_card['type_line']} | {selected_card['oracle_text']}"
        )
        # Use the card's color identity for the search
        search_color = "".join(selected_card["color_identity"])

    # Step 1: Search Scryfall
    with st.spinner(f"🔍 Searching for cards..."):
        cards = search_scryfall(creature_type, fmt, search_color, is_arena)

    if not cards:
        st.warning("⚠️ No cards found. Try different colors, format, or creature type.")
        return

    st.success(f"✅ Found **{len(cards)}** cards! Sending to Claude...")

    # Store images
    st.session_state.card_images = {
        c["name"]: c["image_url"] for c in cards if c["image_url"]
    }

    # Step 2: Format card data
    card_text = format_card_data(cards)

    # Step 3: Build deck with AI
    spinner_msg = "🤖 Claude is building your deck"
    if card_name:
        spinner_msg += f" around **{card_name}**"
    spinner_msg += "... This may take 15–30 seconds."

    with st.spinner(spinner_msg):
        result = build_deck_with_ai(
            card_text, creature_type, fmt, strat, budget,
            platform, card_name=card_name, card_info=card_info
        )

    if result:
        st.session_state.deck_result = result

# ─────────────────────────────────────────────
# DECK CONFIGURATION PANEL (when a card is selected)
# ─────────────────────────────────────────────
if st.session_state.show_config and st.session_state.selected_card:
    card = st.session_state.selected_card

    st.markdown("## ⚔️ Build Around This Card")

    config_col1, config_col2 = st.columns([1, 2])

    with config_col1:
        if card["image_url"]:
            st.image(card["image_url"], use_container_width=True)

    with config_col2:
        st.markdown(f"### {card['name']}")
        st.markdown(f"**{card['type_line']}**")
        st.markdown(f"**Colors:** {card['color_symbols']}")
        if card["oracle_text"]:
            st.caption(card["oracle_text"][:300])

        st.markdown("---")
        st.markdown("**Choose your deck settings:**")

        config_format = st.selectbox(
            "📜 Format",
            ["Commander", "Modern", "Standard", "Pioneer", "Pauper"],
            key="config_format",
            help="Commander uses this card as your commander. Other formats use it as the build-around centerpiece."
        )

        config_strategy = st.selectbox(
            "🎯 Strategy",
            ["Aggressive", "Midrange", "Control", "Combo"],
            key="config_strategy"
        )

        build_col, cancel_col = st.columns(2)
        with build_col:
            if st.button("🚀 Build This Deck!", key="confirm_build", use_container_width=True):
                st.session_state.show_config = False
                st.session_state.deck_result = None
                run_deck_build(
                    selected_card=card,
                    format_override=config_format,
                    strategy_override=config_strategy
                )
        with cancel_col:
            if st.button("❌ Cancel", key="cancel_build", use_container_width=True):
                st.session_state.show_config = False
                st.session_state.selected_card = None
                st.rerun()

    st.markdown("---")

# ─────────────────────────────────────────────
# Handle Custom Deck Button (sidebar)
# ─────────────────────────────────────────────
if build_custom_button:
    if not creature_type.strip() and not color_identity:
        st.warning("⚠️ Please enter a creature type or select at least one color!")
    else:
        st.session_state.deck_result = None
        st.session_state.show_config = False
        st.session_state.selected_card = None
        run_deck_build(selected_card=None)

# ─────────────────────────────────────────────
# Display Deck Results (if any)
# ─────────────────────────────────────────────
if st.session_state.deck_result:
    st.markdown("---")
    st.markdown("## 📋 Your AI-Generated Deck")
    st.markdown(st.session_state.deck_result)

    # Export Button
    st.markdown("---")
    st.download_button(
        label="📥 Download Decklist as Text File",
        data=st.session_state.deck_result,
        file_name="mtg_deck.txt",
        mime="text/plain",
        use_container_width=True
    )

    # Card Image Gallery
    if st.session_state.card_images:
        st.markdown("---")
        st.markdown("## 🖼️ Card Gallery")
        st.caption("Showing card images from the Scryfall search results used by the AI.")
        image_items = list(st.session_state.card_images.items())[:40]
        cols = st.columns(4)
        for idx, (name, url) in enumerate(image_items):
            with cols[idx % 4]:
                st.image(url, caption=name, use_container_width=True)

    # Button to go back to the home screen
    st.markdown("---")
    if st.button("🏠 Back to Home — Build Another Deck", use_container_width=True):
        st.session_state.deck_result = None
        st.session_state.card_images = {}
        st.session_state.selected_card = None
        st.session_state.show_config = False
        st.rerun()

# ─────────────────────────────────────────────
# Popular Cards Section (Home Screen)
# ─────────────────────────────────────────────
if st.session_state.deck_result is None and not st.session_state.show_config:
    st.markdown("## 🏆 Popular Legendary Cards")

    platform_label = "🎮 Arena" if is_arena else "🃏 Paper"
    if color_identity:
        color_map = {"W": "⚪ White", "U": "🔵 Blue", "B": "⚫ Black", "R": "🔴 Red", "G": "🟢 Green"}
        selected_names = [color_map[c] for c in selected_colors]
        st.caption(
            f"Showing top legendary cards in: {', '.join(selected_names)} | "
            f"Platform: {platform_label}"
        )
    else:
        st.caption(
            f"Showing the most popular legendary cards across all colors | "
            f"Platform: {platform_label} | Select colors in the sidebar to filter."
        )

    with st.spinner("Loading popular cards..."):
        popular_cards = fetch_popular_cards(color_identity, is_arena)

    if popular_cards:
        st.markdown(
            "**👆 Click any card below to build a deck around it — "
            "you can choose Commander, Modern, Standard, or any format!**"
        )
        st.markdown("")

        cols = st.columns(4)
        for idx, card in enumerate(popular_cards):
            with cols[idx % 4]:
                if card["image_url"]:
                    st.image(card["image_url"], use_container_width=True)
                st.markdown(f"**{card['name']}**")
                st.caption(f"{card['color_symbols']} · {card['type_line']}")
                if st.button(f"⚔️ Build Deck", key=f"card_{idx}"):
                    st.session_state.selected_card = card
                    st.session_state.show_config = True
                    st.session_state.deck_result = None
                    st.rerun()
    else:
        st.warning("No cards found for the selected colors. Try different colors or platform.")

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
