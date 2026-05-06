package audit.enforcement.resource.check.policy_0752

# Auto-generated policy 752 (Rego v1 syntax)
# Package: audit.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0752",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0752_allowed if {
    input.user.active
    input.resource.public
}
policy_0752_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0752_allowed = false
policy_0752_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
