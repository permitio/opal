package audit.authentication.action.check.policy_0578

# Auto-generated policy 578 (Rego v1 syntax)
# Package: audit.authentication.action.check

# Metadata
metadata := {
    "policy_id": "0578",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0578_allowed if {
    input.user.active
    input.resource.public
}
policy_0578_allowed if {
    data.policies.audit.enabled
}
policy_0578_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0578_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
