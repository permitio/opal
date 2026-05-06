package governance.authentication.policy.check.policy_0350

# Auto-generated policy 350 (Rego v1 syntax)
# Package: governance.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0350",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0350_allowed if {
    input.user.active
    input.resource.public
}
policy_0350_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0350_allowed if {
    data.policies.governance.enabled
}
