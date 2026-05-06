package security.authentication.resource.verify.core.policy_0342

# Auto-generated policy 342 (Rego v1 syntax)
# Package: security.authentication.resource.verify.core

# Metadata
metadata := {
    "policy_id": "0342",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0342_allowed if {
    data.policies.security.enabled
}
policy_0342_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0342_allowed if {
    input.user.role == "admin"
}
