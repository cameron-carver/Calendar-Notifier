/**
 * Alpine.js dashboard application logic
 */
function dashboardApp() {
    return {
        activeTab: 'settings',
        settings: {
            delivery_schedule: {
                monday: '',
                tuesday: '',
                wednesday: '',
                thursday: '',
                friday: '',
                saturday: '',
                sunday: '',
                default: '08:00'
            },
            content_depth: 'standard',
            time_window_hours: 0,
            enable_ai_prep: true,
            enable_news: true,
            enable_meeting_history: true,
            enable_affinity_data: true,
            enable_web_enrichment: true,
            filter_require_non_owner: true,
            filter_external_only: true,
            filter_exclude_recurring: true,
            max_news_articles: 3,
            talking_points_enabled: true
        },
        presets: [],
        metrics: {},
        saving: false,
        loading: false,
        showToast: false,
        toastMessage: '',
        lastBriefDate: 'Loading...',

        async init() {
            console.log('Dashboard initializing...');
            await this.loadSettings();
            await this.loadPresets();
            await this.loadMetrics();
            await this.loadLastBriefDate();
            console.log('Dashboard initialized');
        },

        async loadSettings() {
            try {
                const response = await fetch('/dashboard/settings');
                if (response.ok) {
                    const data = await response.json();
                    console.log('Loaded settings:', data);

                    // Map database settings to form
                    this.settings.content_depth = data.content_depth || 'standard';
                    this.settings.time_window_hours = data.time_window_hours || 0;

                    // Feature toggles (null = use default)
                    this.settings.enable_ai_prep = data.enable_ai_prep !== null ? data.enable_ai_prep : true;
                    this.settings.enable_news = data.enable_news !== null ? data.enable_news : true;
                    this.settings.enable_meeting_history = data.enable_meeting_history !== null ? data.enable_meeting_history : true;
                    this.settings.enable_affinity_data = data.enable_affinity_data !== null ? data.enable_affinity_data : true;
                    this.settings.enable_web_enrichment = data.enable_web_enrichment !== null ? data.enable_web_enrichment : true;

                    // Filters
                    this.settings.filter_require_non_owner = data.filter_require_non_owner !== null ? data.filter_require_non_owner : true;
                    this.settings.filter_external_only = data.filter_external_only !== null ? data.filter_external_only : true;
                    this.settings.filter_exclude_recurring = data.filter_exclude_recurring !== null ? data.filter_exclude_recurring : true;

                    // Delivery schedule
                    if (data.delivery_schedule) {
                        this.settings.delivery_schedule = {
                            ...this.settings.delivery_schedule,
                            ...data.delivery_schedule
                        };
                    }

                    // Content limits
                    this.settings.max_news_articles = data.max_news_articles || 3;
                    this.settings.talking_points_enabled = data.talking_points_enabled !== null ? data.talking_points_enabled : true;
                } else {
                    console.error('Failed to load settings:', response.status);
                }
            } catch (error) {
                console.error('Error loading settings:', error);
                this.toast('Failed to load settings', true);
            }
        },

        async saveSettings() {
            this.saving = true;
            try {
                console.log('Saving settings:', this.settings);

                // Clean up delivery schedule (remove empty values)
                const cleanedSchedule = {};
                for (const [day, time] of Object.entries(this.settings.delivery_schedule)) {
                    if (time && time.trim() !== '') {
                        cleanedSchedule[day] = time;
                    }
                }

                const payload = {
                    ...this.settings,
                    delivery_schedule: Object.keys(cleanedSchedule).length > 0 ? cleanedSchedule : null
                };

                const response = await fetch('/dashboard/settings', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    const data = await response.json();
                    console.log('Settings saved:', data);
                    this.toast('Settings saved successfully!');
                } else {
                    const error = await response.json();
                    console.error('Failed to save settings:', error);
                    this.toast('Failed to save settings: ' + (error.detail || 'Unknown error'), true);
                }
            } catch (error) {
                console.error('Error saving settings:', error);
                this.toast('Error saving settings', true);
            } finally {
                this.saving = false;
            }
        },

        async resetToDefaults() {
            if (!confirm('Reset all settings to defaults?')) {
                return;
            }

            this.settings = {
                delivery_schedule: {
                    monday: '',
                    tuesday: '',
                    wednesday: '',
                    thursday: '',
                    friday: '',
                    saturday: '',
                    sunday: '',
                    default: '08:00'
                },
                content_depth: 'standard',
                time_window_hours: 0,
                enable_ai_prep: true,
                enable_news: true,
                enable_meeting_history: true,
                enable_affinity_data: true,
                enable_web_enrichment: true,
                filter_require_non_owner: true,
                filter_external_only: true,
                filter_exclude_recurring: true,
                max_news_articles: 3,
                talking_points_enabled: true
            };

            await this.saveSettings();
        },

        async loadPresets() {
            try {
                const response = await fetch('/dashboard/presets');
                if (response.ok) {
                    this.presets = await response.json();
                    console.log('Loaded presets:', this.presets);
                } else {
                    console.error('Failed to load presets:', response.status);
                }
            } catch (error) {
                console.error('Error loading presets:', error);
            }
        },

        async activatePreset(presetId) {
            try {
                console.log('Activating preset:', presetId);
                const response = await fetch(`/dashboard/presets/${presetId}/activate`, {
                    method: 'POST'
                });

                if (response.ok) {
                    const data = await response.json();
                    console.log('Preset activated:', data);
                    await this.loadPresets();
                    await this.loadSettings();
                    this.toast(`Activated preset: ${data.name}`);
                } else {
                    console.error('Failed to activate preset:', response.status);
                    this.toast('Failed to activate preset', true);
                }
            } catch (error) {
                console.error('Error activating preset:', error);
                this.toast('Error activating preset', true);
            }
        },

        async loadMetrics() {
            try {
                const response = await fetch('/dashboard/metrics?days=30');
                if (response.ok) {
                    this.metrics = await response.json();
                    console.log('Loaded metrics:', this.metrics);
                } else {
                    console.error('Failed to load metrics:', response.status);
                    this.metrics = {
                        total_briefs: 0,
                        total_meetings: 0,
                        total_tokens: 0,
                        avg_generation_time: 0,
                        enrichment_rate: 0,
                        meetings_with_ai_prep: 0,
                        linkedin_found: 0,
                        news_articles_found: 0,
                        company_data_found: 0
                    };
                }
            } catch (error) {
                console.error('Error loading metrics:', error);
                this.metrics = {
                    total_briefs: 0,
                    total_meetings: 0,
                    total_tokens: 0,
                    avg_generation_time: 0,
                    enrichment_rate: 0,
                    meetings_with_ai_prep: 0,
                    linkedin_found: 0,
                    news_articles_found: 0,
                    company_data_found: 0
                };
            }
        },

        async loadLastBriefDate() {
            try {
                const response = await fetch('/briefs/history?limit=1');
                if (response.ok) {
                    const data = await response.json();
                    console.log('Last brief:', data);
                    if (data.length > 0) {
                        const date = new Date(data[0].created_at);
                        this.lastBriefDate = date.toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric'
                        });
                    } else {
                        this.lastBriefDate = 'Never';
                    }
                } else {
                    this.lastBriefDate = 'Unknown';
                }
            } catch (error) {
                console.error('Error loading last brief date:', error);
                this.lastBriefDate = 'Error';
            }
        },

        toast(message, isError = false) {
            this.toastMessage = message;
            this.showToast = true;
            setTimeout(() => {
                this.showToast = false;
            }, 3000);
        }
    };
}
