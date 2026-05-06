package audit.validation.policy.verify.policy_0631

# Auto-generated policy 631 (Rego v1 syntax)
# Package: audit.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0631",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0631_allowed = false
policy_0631_allowed if {
    input.user.active
    input.resource.public
}
policy_0631_allowed if {
    data.policies.audit.enabled
}
policy_0631_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
