import json
from typing import Any, get_type_hints

from pydantic import BaseModel, ValidationError

from .custom_types import RouteHandler
from .request import Request
from .response import (
    JSONResponse,
    NotFoundErrorResponse,
    Response,
    ValidationErrorResponse,
)


def handle_request(request: Request, handlers: list[RouteHandler]) -> Response:
    """
    A method that tries to find the matching route handler.
    """

    for handler in handlers:
        # ? Check dynamic routes
        is_dynamic = False
        if "{" in handler["path"] and "}" in handler["path"]:  # ['/greet/{name}']
            # ? Ignore first slash
            # ! This wont work for trailing backslash
            handler_path = handler["path"].split("/")[1:]  # path = ['greet', '{name}']
            request_path = request.path.split("/")[1:]
            if len(handler_path) == len(request_path):
                is_dynamic = True
                for handler_part, request_part in zip(handler_path, request_path):
                    if (
                        handler_part[0] == "{" and handler_part[-1] == "}"
                    ):  # handler_part = '{name}'
                        request.params[handler_part[1:-1]] = request_part

        if handler["method"] == request.method and (
            handler["path"] == request.path or is_dynamic
        ):
            # Apply middleware
            for middleware in handler["middleware"]:
                middleware(request)
            handler_type_hints = get_type_hints(handler["handler"])
            dependency_injection: dict[str, Any] = {}
            for k, v in handler_type_hints.items():
                if v == Request:
                    dependency_injection[k] = request
                elif k in request.body.keys():
                    if isinstance(request.body[k], v):
                        dependency_injection[k] = request.body[k]
                    elif type(v) == type(BaseModel):
                        try:
                            dependency_injection[k] = v.parse_obj(request.body[k])
                        except ValidationError as e:
                            return ValidationErrorResponse(
                                messages={"errors": e.errors()}  # type: ignore
                            )
                    else:
                        return ValidationErrorResponse(
                            messages={
                                "errors": [
                                    {
                                        "loc": [k],
                                        "msg": f"Property {k} is required to be of type {v.__name__}",
                                    }
                                ]
                            }
                        )
                else:
                    return ValidationErrorResponse(
                        messages={
                            "errors": [
                                {
                                    "loc": [k],
                                    "msg": f"Property {k} is required to be of type {v.__name__} but it's missing",
                                }
                            ]
                        }
                    )
            if handler_type_hints and not dependency_injection:
                return ValidationErrorResponse(
                    messages={
                        "errors": [
                            {"loc": ["body"], "msg": "Required fields are not supplied"}
                        ]
                    }
                )
            response = handler["handler"](**dependency_injection)
            if isinstance(response, str):
                constructed_response = Response(
                    code=200, body=response, content_type="string"
                )
            elif isinstance(response, (int, float)):
                constructed_response = Response(
                    code=200, body=str(response), content_type="string"
                )
            elif isinstance(response, JSONResponse):
                constructed_response = response
            elif isinstance(response, Response):
                constructed_response = response
            elif isinstance(response, BaseModel):
                # Pydantic BaseModel
                constructed_response = Response(
                    code=200,
                    body=response.json(),
                    content_type="application/json",
                )
            elif isinstance(response, dict):
                # Dict
                constructed_response = Response(
                    code=200,
                    body=json.dumps(response),
                    content_type="application/json",
                )
            else:
                raise Exception("Unsupported Return Type from View Function")
            return constructed_response
    return NotFoundErrorResponse()
