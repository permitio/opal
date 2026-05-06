package compliance.validation.resource.allow.utils.policy_0368

# Auto-generated policy 368 (Rego v1 syntax)
# Package: compliance.validation.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0368",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0368_allowed if {
    input.user.role == "admin"
}
policy_0368_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
