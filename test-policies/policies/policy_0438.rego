package access.validation.action.verify.policy_0438

# Auto-generated policy 438 (Rego v1 syntax)
# Package: access.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0438",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0438_allowed if {
    input.user.role == "admin"
}
policy_0438_allowed if {
    input.user.active
    input.resource.public
}
policy_0438_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
