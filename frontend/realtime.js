
const button = document.querySelector("#refresh-realtime");
const placeInput = document.querySelector("#realtime-place");
const statusEl = document.querySelector("#realtime-status");
const weatherEl = document.querySelector("#realtime-weather");
const alertsEl = document.querySelector("#realtime-alerts");
const roadsEl = document.querySelector("#realtime-roads");
const mapEl = document.querySelector("#realtime-map");

function addText(parent, tag, value) {
    const el = document.createElement(tag);
    el.textContent = String(value ?? "Not provided");
    parent.appendChild(el);
    return el;
}

async function loadRealtime() {
    const place = placeInput.value.trim();

    if (!place) {
        statusEl.textContent = "Enter a location first.";
        return;
    }

    button.disabled = true;
    statusEl.textContent = "Loading live data...";

    try {
        const response = await fetch(
            `/api/realtime?place=${encodeURIComponent(place)}`
        );
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
        }

        // Weather cards
        weatherEl.replaceChildren();
        const weather = data.weather?.current ?? {};
        const grid = document.createElement("div");
        grid.className = "weather-grid";

        const cards = [
            ["Temperature", weather.temperature_2m, "°C"],
            ["Feels Like", weather.apparent_temperature, "°C"],
            ["Humidity", weather.relative_humidity_2m, "%"],
            ["Wind Speed", weather.wind_speed_10m, "km/h"],
            ["Wind Gusts", weather.wind_gusts_10m, "km/h"],
            ["Precipitation", weather.precipitation, "mm"]
        ];

        for (const [label, value, unit] of cards) {
            const card = document.createElement("div");
            card.className = "weather-card";
            addText(card, "h4", label);

            const reading = addText(
                card,
                "p",
                typeof value === "number" ? `${value} ${unit}` : "Unavailable"
            );
            reading.className = "weather-value";
            grid.appendChild(card);
        }

        weatherEl.appendChild(grid);

        const source = addText(
            weatherEl,
            "p",
            `Source: ${data.weather?.provider ?? "Unknown"} | ` +
            `Updated: ${weather.time ?? "Unknown"}`
        );
        source.className = "weather-source";

        // Official alerts
        alertsEl.replaceChildren();
        addText(
            alertsEl,
            "p",
            `Alert feed status: ${data.alerts?.status ?? "unknown"}`
        );

        for (const item of data.alerts?.sources ?? []) {
            addText(alertsEl, "p", `${item.name}: ${item.status}`);

            if (item.error) {
                addText(alertsEl, "p", item.error);
            }
        }

        const alertList = data.alerts?.alerts ?? [];

        for (const alert of alertList) {
            const article = document.createElement("article");
            addText(article, "h4", alert.area || "Official alert");
            addText(article, "p", alert.message || "See official record.");

            if (alert.source_url) {
                const link = addText(
                    article,
                    "a",
                    alert.source || "View official source"
                );
                link.href = alert.source_url;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
            }

            alertsEl.appendChild(article);
        }

        if (alertList.length === 0) {
            addText(
                alertsEl,
                "p",
                "No matching alert records returned. This does not mean the area is safe."
            );
        }

        // Road status and official sources
        roadsEl.replaceChildren();
        addText(
            roadsEl,
            "h4",
            `Road status: ${data.roads?.road_status ?? "unknown"}`
        );
        addText(
            roadsEl,
            "p",
            data.roads?.message || "Verified road status unavailable."
        );

        for (const item of data.roads?.official_sources ?? []) {
            const link = addText(roadsEl, "a", item.name);
            link.href = item.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            roadsEl.appendChild(document.createElement("br"));
        }

        for (const contact of data.roads?.emergency_contacts ?? []) {
            addText(
                roadsEl,
                "p",
                `${contact.name}: ${contact.phone}`
            );
        }

        // Map
        mapEl.replaceChildren();

        if (data.map?.map_url) {
            const link = addText(
                mapEl,
                "a",
                `Open ${place} in OpenStreetMap`
            );
            link.href = data.map.map_url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";

            const coords = data.map.coordinates;
            if (coords) {
                addText(
                    mapEl,
                    "p",
                    `Coordinates: ${coords.latitude}, ${coords.longitude}`
                );
            }
        } else {
            addText(mapEl, "p", "Map unavailable: location not resolved.");
        }

        statusEl.textContent =
            `Retrieved: ${data.retrieved_at_utc}. ` +
            "Decision support only; not a safety clearance.";

    } catch (error) {
        statusEl.textContent = `Request failed: ${error.message}`;
        console.error("Live data request failed:", error);
    } finally {
        button.disabled = false;
    }
}

if (
    button && placeInput && statusEl &&
    weatherEl && alertsEl && roadsEl && mapEl
) {
    button.addEventListener("click", loadRealtime);
} else {
    console.error("Real-time panel HTML elements are missing.");
}
