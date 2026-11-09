def test_fake_root_isolates_everything(book, fake_root):
    import layout
    from studio_app import config, projects
    assert layout.find_dir("demo") == book and fake_root == config.ROOT
    assert [p["slug"] if isinstance(p, dict) and "slug" in p else p for p in [projects.project_info("demo")]]
