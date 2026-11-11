"""Streamlit controls for explicit start/load/resume; reruns only read snapshots."""
from uuid import uuid4
import streamlit as st
from src.discovery_agent import DiscoveryError
from src.persistence import start_run, load_run, review_run, continue_run, regenerate_briefing
from src.workflow_guide import render_workflow_guide


def render_full_workflow(company, industry, requested=False):
    st.header('Full research workflow')
    st.caption('Verification → bounded evidence repair → human review → approved briefing. Run IDs are saved in the page URL.')
    guide = st.empty()
    run_id = st.session_state.get('full_run_id') or st.query_params.get('run', '')
    if requested:
        run_id = str(uuid4())
        st.session_state.full_run_id = run_id
        st.query_params['run'] = run_id
        try:
            with st.status('Running full research…', expanded=True) as status:
                step = st.empty()
                saved = st.session_state.get('discovery_result', {})
                selected = saved.get('competitors') if st.session_state.get('discovery_target') == (company.strip(), industry.strip()) else None
                start_run(run_id, company, industry, competitors=selected, progress=step.text)
                status.update(label='Saved research run — review status below', state='complete', expanded=False)
        except DiscoveryError as error:
            st.error(str(error))
        except Exception:
            st.error('Workflow stopped. Its last completed checkpoint is saved; load the run to continue. Check sanitized terminal diagnostics.')

    saved_id = st.text_area('Saved research run ID', value=run_id or '', key='saved_run_id', max_chars=80)
    if st.button('Load Saved Run', key='load_saved_run'):
        run_id = saved_id.strip()
        st.session_state.full_run_id = run_id
        st.query_params['run'] = run_id
    if not run_id:
        with guide.container():
            render_workflow_guide()
        return
    try:
        state = load_run(run_id)
        with guide.container():
            render_workflow_guide(state)
        if not state:
            st.info('This run ID is not available in the current database. Saved runs belong to the '
                    'database and deployment environment where they were created: a run created locally '
                    'may not exist on Streamlit Cloud. Cloud-local checkpoints can also be lost after '
                    'restarts or redeployments. Check the run ID and the environment where you created it. '
                    'To start a new research run here, enter the company and industry above and select '
                    'Run Full Research.')
            return
        st.code(run_id, language=None)
        st.text(f"{state.get('company')} · {state.get('industry')} · Status: {state.get('approval_status')}")
        st.caption(f"Automatic repair cycles: {state.get('repair_count', 0)}/2 · Human revisions: {state.get('revision_count', 0)}/2")
        if state.get('workflow_error'):
            st.error(state['workflow_error'])
        if state.get('_pending_nodes') and not state.get('_interrupted'):
            st.info('A saved execution is incomplete. Continuing may call research providers.')
            if st.button('Continue Saved Run', key='continue_run'):
                with st.spinner('Continuing saved research…'):
                    continue_run(run_id)
                st.rerun()
        for name, fields in state.get('verification', {}).items():
            st.subheader(f'{name} — verification summary')
            for field, findings in fields.items():
                for finding in findings:
                    st.text(f"{field}: {finding['status']} — {finding['context'] or finding['value']}")
                    for url in finding['evidence_urls']:
                        st.link_button('Review evidence', url)
        warnings = list(dict.fromkeys(state.get('gaps', []) + state.get('errors', [])))
        if warnings:
            st.warning('Evidence is incomplete or conflicting. Approval will not turn these gaps into verified facts.')
            with st.expander('Verification warnings and research gaps', expanded=True):
                for warning in warnings:
                    st.text(warning)
        if state.get('approval_status') == 'pending' and state.get('_interrupted'):
            token = state['review_token']
            with st.form(f'review_{token}'):
                st.text('Review the findings, sources, and unresolved gaps before approving a report.')
                feedback = st.text_area('Revision instructions', max_chars=500)
                approve = st.form_submit_button('Approve', key=f'approve_{token}')
                revise = st.form_submit_button('Request Revision', key=f'revise_{token}')
                reject = st.form_submit_button('Reject', key=f'reject_{token}')
            if approve or revise or reject:
                with st.spinner('Saving review decision…'):
                    review_run(run_id, 'approve' if approve else 'revise' if revise else 'reject',
                               token, feedback=feedback)
                st.rerun()
        if state.get('approval_status') == 'approved' and state.get('final_report'):
            st.header('Approved competitor briefing')
            st.caption('Regeneration formats saved verified evidence only. It does not call research providers or repeat approval; previous reports are retained.')
            if st.button('Regenerate Briefing from Saved Evidence', key='regenerate_briefing'):
                with st.spinner('Formatting saved evidence…'):
                    regenerate_briefing(run_id)
                st.rerun()
            st.markdown(state['final_report'])
            st.download_button('Download Markdown Briefing', state['final_report'],
                               file_name=f'marketintel-{run_id}.md', mime='text/markdown', key='download_briefing')
            if state.get('original_report'):
                with st.expander('Preserved original report'):
                    st.download_button('Download Original Markdown', state['original_report'],
                        file_name=f'marketintel-{run_id}-original.md', mime='text/markdown', key='download_original')
                    st.caption(f"{len(state.get('report_history', []))} prior report version(s) preserved in this run.")
        elif state.get('approval_status') in ('rejected', 'revision_limit_reached'):
            st.info('This run ended without an approved report. You can start a new research run.')
    except DiscoveryError as error:
        st.error(str(error))
    except Exception:
        st.error('Could not load or resume this run. Check database access and sanitized terminal diagnostics.')
