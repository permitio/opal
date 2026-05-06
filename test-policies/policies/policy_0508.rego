package access.validation.user.verify.policy_0508

# Auto-generated policy 508 (Rego v1 syntax)
# Package: access.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0508",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0508_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0508_allowed if {
    data.policies.access.enabled
}
