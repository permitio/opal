package security.validation.resource.allow.policy_0286

# Auto-generated policy 286 (Rego v1 syntax)
# Package: security.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0286",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0286_allowed if {
    input.user.role == "admin"
}
policy_0286_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
