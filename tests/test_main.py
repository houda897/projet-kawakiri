import main


def test_run_all_executes_validations_before_certification_and_report(monkeypatch) -> None:
    calls = []
    identifiability_call_count = 0

    step_names = [
        "run_folder_ingestion",
        "run_basic_profile",
        "run_identifiability",
        "run_source_pk_inference",
        "run_source_join_inference",
        "run_functional_group_inference",
        "run_logical_table_building",
        "run_logical_table_profile",
        "run_identifiability",
        "run_pk_inference:LOGICAL",
        "run_join_inference:LOGICAL",
        "run_adjacency",
        "run_table_roles",
        "run_model_candidate_building",
        "run_model_ranking",
        "run_structural_validation",
        "run_granularity_validation",
        "run_semantic_homogeneity_validation",
        "run_aggregation_stability_validation",
        "run_model_certification",
        "run_sql_view_generation",
        "run_certification_report_export",
    ]

    def fake_identifiability() -> None:
        nonlocal identifiability_call_count
        calls.append(f"run_identifiability:{identifiability_call_count}")
        identifiability_call_count += 1

    patched_names = {step_name.split(":", 1)[0] for step_name in step_names}
    for step_name in patched_names:
        if step_name == "run_folder_ingestion":
            monkeypatch.setattr(
                main,
                step_name,
                lambda path, current_step=step_name: calls.append(current_step) or ["source_table"],
            )
        elif step_name == "run_logical_table_building":
            monkeypatch.setattr(
                main,
                step_name,
                lambda current_step=step_name: calls.append(current_step) or ["logical_table"],
            )
        elif step_name == "run_pk_inference":
            monkeypatch.setattr(
                main,
                step_name,
                lambda *args, **kwargs: calls.append(
                    f"run_pk_inference:{kwargs.get('analysis_scope', 'LOGICAL')}"
                ),
            )
        elif step_name == "run_join_inference":
            monkeypatch.setattr(
                main,
                step_name,
                lambda *args, **kwargs: calls.append(
                    f"run_join_inference:{kwargs.get('analysis_scope', 'LOGICAL')}"
                ),
            )
        elif step_name == "run_certification_report_export":
            monkeypatch.setattr(
                main,
                step_name,
                lambda path, current_step=step_name: calls.append(current_step),
            )
        elif step_name == "run_identifiability":
            monkeypatch.setattr(main, step_name, fake_identifiability)
        else:
            monkeypatch.setattr(
                main,
                step_name,
                lambda *args, current_step=step_name, **kwargs: calls.append(current_step),
            )

    main.run_all("csv-folder", "report.json", skip_sql_views=False)

    identifiability_seen = 0
    expected_calls = []
    for step_name in step_names:
        if step_name == "run_identifiability":
            expected_calls.append(f"run_identifiability:{identifiability_seen}")
            identifiability_seen += 1
        else:
            expected_calls.append(step_name)

    assert calls == expected_calls
    assert calls.index("run_semantic_homogeneity_validation") < calls.index(
        "run_aggregation_stability_validation"
    )
    assert calls.index("run_aggregation_stability_validation") < calls.index(
        "run_model_certification"
    )
    assert calls.index("run_model_certification") < calls.index("run_certification_report_export")
    assert calls.index("run_functional_group_inference") < calls.index("run_logical_table_building")
    assert calls.index("run_logical_table_profile") < calls.index("run_pk_inference:LOGICAL")
