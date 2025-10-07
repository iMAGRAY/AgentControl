from backend import app


def test_handler_default():
    response = app.handler()
    assert response["message"] == "backend-ok"
