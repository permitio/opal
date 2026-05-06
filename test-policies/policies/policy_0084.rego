package audit.authentication.user.verify.core.policy_0084

# Auto-generated policy 84 (Rego v1 syntax)
# Package: audit.authentication.user.verify.core

# Metadata
metadata := {
    "policy_id": "0084",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0084_allowed if {
    data.policies.audit.enabled
}
policy_0084_allowed if {
    input.user.active
    input.resource.public
}
