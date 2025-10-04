from backend import handler


def test_handler_default():
    response = handler()
    assert response["message"] == "backend-ok"
