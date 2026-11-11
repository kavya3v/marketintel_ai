import streamlit as st
from src.discovery_agent import DiscoveryError, discover_competitors
from src.graph import generate_research_profiles
from src.workflow_ui import render_full_workflow

st.set_page_config(page_title='MarketIntel AI', page_icon=':material/search:')
st.title('MarketIntel AI — Competitor Research Agent')
st.caption('Find up to three competitors using live web evidence from Tavily and Fireworks AI.')

with st.form('discovery'):
    company = st.text_input('Company', value='Notion', key='company')
    industry = st.text_input('Industry', value='Productivity software', key='industry')
    submitted = st.form_submit_button('Discover Competitors', type='primary')
    full_requested = st.form_submit_button('Run Full Research', key='run_full')

if submitted:
    st.session_state.pop('research_result', None)
    st.session_state.pop('discovery_result', None)
    st.session_state.pop('discovery_target', None)
    try:
        with st.spinner('Planning searches and checking competitor evidence…'):
            result = discover_competitors(company, industry)
        st.session_state.discovery_result = result
        st.session_state.discovery_target = (company.strip(), industry.strip())
    except DiscoveryError as error:
        st.error(str(error))
    except Exception:
        st.error('Competitor discovery failed unexpectedly. Check provider configuration and try again.')

if 'discovery_result' in st.session_state:
    result = st.session_state.discovery_result
    target, market = st.session_state.discovery_target
    st.text(f'Results for {target} · {market}')
    competitors = result['competitors']
    if len(competitors) < 3:
        st.info(f'Found {len(competitors)} evidence-supported competitor(s). Insufficient evidence for three.')
    st.caption('Names, citations, and website URLs are checked against Tavily results. Selection rationales are AI summaries of that evidence.')
    for competitor in competitors:
        with st.container(border=True):
            st.subheader(competitor.name)
            st.link_button('Website', competitor.website)
            st.text(competitor.rationale)
            st.caption('Sources')
            for index, url in enumerate(competitor.source_urls, 1):
                st.link_button(f'Source {index}', url)

    if st.button('Generate Research Profiles', key='generate_profiles', type='primary'):
        st.session_state.pop('research_result', None)
        try:
            with st.status('Researching competitor profiles…', expanded=True) as status:
                current_step = st.empty()
                research_state = dict(result, company=target, industry=market)
                profiles = generate_research_profiles(research_state, progress=current_step.text)
                st.session_state.research_result = profiles
                status.update(label='Research finished — review evidence and gaps below', state='complete', expanded=False)
        except DiscoveryError as error:
            st.error(str(error))
        except Exception:
            st.error('Research profile generation failed. Check provider configuration and try again.')

    if 'research_result' in st.session_state:
        research_state = st.session_state.research_result
        st.header('Research profiles')
        st.caption('Verified facts are literal excerpts checked against retrieved sources; they are not independently audited. Strategic inferences are labeled separately.')
        for message in research_state.get('errors', []):
            st.warning(message)
        for name, profile in research_state.get('profiles', {}).items():
            with st.container(border=True):
                st.subheader(name)
                for field, label in [('pricing', 'Pricing'), ('core_features', 'Core features'),
                                     ('target_customers', 'Target customers'), ('positioning', 'Positioning'),
                                     ('recent_news', 'Recent news')]:
                    st.markdown(f'**{label}**')
                    for claim in getattr(profile, field):
                        status_label = {'verified': 'Source-supported fact', 'inferred': 'Strategic inference',
                                        'not_verified': 'Not verified'}[claim.status]
                        st.text(f'{status_label}: {claim.value}')
                        if field == 'recent_news':
                            st.caption(f'Publication date: {claim.publication_date}')
                        for url in claim.evidence_urls:
                            st.link_button('Evidence source', url)
                st.markdown('**Research gaps**')
                for gap in profile.missing_information:
                    st.text(gap)
                with st.expander('Retrieved sources'):
                    for source in research_state.get('research', {}).get(name, {}).get('sources', []):
                        st.link_button(source.title or source.url, source.url)
                        st.caption(f'{source.category} · {"Official vendor" if source.official else "External source"} · Retrieved {source.retrieved_at}')
                        if source.publication_date:
                            st.caption(f'Published: {source.publication_date}')
                        st.text(source.snippet)

render_full_workflow(company, industry, full_requested)
