package access.enforcement.context.check.core.policy_0082

# Auto-generated policy 82 (Rego v1 syntax)
# Package: access.enforcement.context.check.core

# Metadata
metadata := {
    "policy_id": "0082",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0082_allowed = false
policy_0082_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0082_allowed if {
    data.policies.access.enabled
}
