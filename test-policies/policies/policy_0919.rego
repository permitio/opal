package audit.authentication.policy.deny.helpers.policy_0919

# Auto-generated policy 919 (Rego v1 syntax)
# Package: audit.authentication.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0919",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0919_allowed if {
    data.policies.audit.enabled
}
policy_0919_allowed if {
    input.user.active
    input.resource.public
}
policy_0919_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0919_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
