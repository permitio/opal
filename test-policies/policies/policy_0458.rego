package governance.validation.policy.allow.data.policy_0458

# Auto-generated policy 458 (Rego v1 syntax)
# Package: governance.validation.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0458",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0458_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0458_allowed if {
    input.user.active
    input.resource.public
}
