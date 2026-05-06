package risk.validation.user.allow.policy_0383

# Auto-generated policy 383 (Rego v1 syntax)
# Package: risk.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0383",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0383_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0383_allowed = false
policy_0383_allowed if {
    data.policies.risk.enabled
}
policy_0383_allowed if {
    input.user.active
    input.resource.public
}
