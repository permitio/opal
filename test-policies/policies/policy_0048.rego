package compliance.enforcement.user.validate.policy_0048

# Auto-generated policy 48 (Rego v1 syntax)
# Package: compliance.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0048",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0048_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0048_allowed if {
    input.user.active
    input.resource.public
}
