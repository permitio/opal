package governance.authentication.context.verify.policy_0093

# Auto-generated policy 93 (Rego v1 syntax)
# Package: governance.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0093",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0093_allowed = false
policy_0093_allowed if {
    data.policies.governance.enabled
}
policy_0093_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0093_allowed if {
    input.user.role == "admin"
}
